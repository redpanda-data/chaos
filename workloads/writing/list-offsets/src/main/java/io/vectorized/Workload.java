package io.vectorized;
import java.io.*;
import java.util.Properties;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.CommonClientConfigs;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import java.util.concurrent.ExecutionException;
import java.lang.Thread;
import org.apache.kafka.common.errors.TimeoutException;
import org.apache.kafka.common.errors.NotLeaderOrFollowerException;
import java.io.BufferedWriter;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.IsolationLevel;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.admin.ListOffsetsOptions;

public class Workload {
    public volatile long succeeded_writes = 0;
    public volatile long failed_writes = 0;
    public volatile long timedout_writes = 0;
    public volatile boolean is_active = false;
    
    private volatile App.InitBody args;
    private volatile ArrayList<Thread> threads;
    private BufferedWriter opslog;
    private long past_us;
    private long known_offset;
    private long before_us = -1;
    private long last_op = 0;

    synchronized long get_op() {
        return ++this.last_op;
    }

    synchronized void update_known_offset(long offset) {
        known_offset = Math.max(known_offset, offset);
    }

    synchronized long get_known_offset() {
        return known_offset;
    }

    public Workload(App.InitBody args) {
        this.args = args;
    }

    public void start() throws Exception {
        File root = new File(args.experiment, args.server);

        if (!root.mkdir()) {
            throw new Exception("Can't create folder: " + root);
        }

        is_active = true;
        past_us = 0;
        update_known_offset(-1);
        opslog = new BufferedWriter(new FileWriter(new File(new File(args.experiment, args.server), "workload.log")));
        
        threads = new ArrayList<>();
        int i=0;

        for (;i<this.args.settings.concurrency;i++) {
            final var j=i;
            threads.add(new Thread(() -> { 
                try {
                    process(j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                }
            }));
        }

        {
            final var j=i++;
            threads.add(new Thread(() -> { 
                try {
                    listOffsetProcess(j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                }
            }));
        }
        
        for (var th : threads) {
            th.start();
        }
    }

    public void stop() throws Exception {
        is_active = false;
        for (var th : threads) {
            th.join();
        }
        if (opslog != null) {
            opslog.flush();
            opslog.close();
        }
    }

    public void event(String name) throws Exception {
        log(-1, "event\t" + name);
    }
    
    private synchronized void log(int thread_id, String message) throws Exception {
        var now_us = System.nanoTime() / 1000;
        if (now_us < past_us) {
            throw new Exception("Time cant go back, observed: " + now_us + " after: " + before_us);
        }
        opslog.write("" + thread_id +
                        "\t" + (now_us - past_us) +
                        "\t" + message + "\n");
        past_us = now_us;
    }

    private void process(int thread_id) throws Exception {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, args.brokers);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, "org.apache.kafka.common.serialization.StringSerializer");
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, "org.apache.kafka.common.serialization.StringSerializer");
        
        // default value: 600000
        props.put(ProducerConfig.CONNECTIONS_MAX_IDLE_MS_CONFIG, 60000);
        // default value: 120000
        props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 10000);
        // default value: 0
        props.put(ProducerConfig.LINGER_MS_CONFIG, 0);
        // default value: 60000
        props.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, 10000);
        // default value: 1000
        props.put(ProducerConfig.RECONNECT_BACKOFF_MAX_MS_CONFIG, 1000);
        // default value: 50
        props.put(ProducerConfig.RECONNECT_BACKOFF_MS_CONFIG, 50);
        // default value: 30000
        props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000);
        // default value: 100
        props.put(ProducerConfig.RETRY_BACKOFF_MS_CONFIG, 100);
        // default value: 300000
        props.put(ProducerConfig.METADATA_MAX_AGE_CONFIG, 10000);
        // default value: 300000
        props.put(ProducerConfig.METADATA_MAX_IDLE_CONFIG, 10000);
        props.put(ProducerConfig.RETRIES_CONFIG, 0);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, false);


        Producer<String, String> producer = null;

        log(thread_id, "started\t" + args.server);

        while (is_active) {
            long op = get_op();
            
            try {
                if (producer == null) {
                    log(thread_id, "constructing");
                    producer = new KafkaProducer<>(props);
                    log(thread_id, "constructed");
                    continue;
                }
            } catch (Exception e) {
                log(thread_id, "err");
                System.out.println(e);
                e.printStackTrace();
                failed_writes++;
                continue;
            }
            
            try {
                log(thread_id, "msg\t" + op);
                var f = producer.send(new ProducerRecord<String, String>(args.topic, args.server, "" + op));
                var m = f.get();
                succeeded_writes++;
                log(thread_id, "ok\t" + m.offset());
                update_known_offset(m.offset());
            } catch (ExecutionException e) {
                var cause = e.getCause();
                if (cause != null) {
                    if (cause instanceof TimeoutException) {
                        log(thread_id, "time");
                        timedout_writes++;
                        continue;
                    } else if (cause instanceof NotLeaderOrFollowerException) {
                        log(thread_id, "err");
                        failed_writes++;
                        continue;
                    }
                }
 
                log(thread_id, "err");
                System.out.println(e);
                failed_writes++;
            } catch (Exception e) {
                log(thread_id, "err");
                System.out.println(e);
                e.printStackTrace();
                failed_writes++;
            }
        }
        producer.close();
    }

    private void listOffsetProcess(int thread_id) throws Exception {
        Properties props = new Properties();
        props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, args.brokers);
        // default value: 600000
        props.put(AdminClientConfig.CONNECTIONS_MAX_IDLE_MS_CONFIG, 60000);
        // default value: 300000
        props.put(AdminClientConfig.METADATA_MAX_AGE_CONFIG, 10000);
        // default value: 1000
        props.put(AdminClientConfig.RECONNECT_BACKOFF_MAX_MS_CONFIG, 1000);
        // default value: 50
        props.put(AdminClientConfig.RECONNECT_BACKOFF_MS_CONFIG, 50);
        // default value: 30000
        props.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000);
        // default value: 100
        props.put(AdminClientConfig.RETRY_BACKOFF_MS_CONFIG, 100);
        // default.api.timeout.ms 60000
        props.put(CommonClientConfigs.DEFAULT_API_TIMEOUT_MS_CONFIG, 10000);
        // request.timeout.ms 30000
        props.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000);
        // default value: 30000
        props.put(AdminClientConfig.SOCKET_CONNECTION_SETUP_TIMEOUT_MAX_MS_CONFIG, 10000);
        // default value: 10000
        props.put(AdminClientConfig.SOCKET_CONNECTION_SETUP_TIMEOUT_MS_CONFIG, 10000);
        props.put(AdminClientConfig.RETRIES_CONFIG, 0);
        props.put(AdminClientConfig.RETRY_BACKOFF_MS_CONFIG, 10000);

        AdminClient client = null;

        log(thread_id, "started\t" + args.server + "\tadmin");

        Map<TopicPartition, OffsetSpec> partitions = new HashMap<>();
        var tp = new TopicPartition(args.topic, 0);
        partitions.put(tp, OffsetSpec.latest());
        var listOffsetsOptions = new ListOffsetsOptions(IsolationLevel.READ_COMMITTED);

        while (is_active) {
            try {
                if (client == null) {
                    log(thread_id, "constructing");
                    client = AdminClient.create(props);
                    log(thread_id, "constructed");
                    continue;
                }
            } catch (Exception e) {
                log(thread_id, "err");
                System.out.println(e);
                e.printStackTrace();
                failed_writes++;
                continue;
            }
            
            try {
                var last_offset = get_known_offset();
                var result = client.listOffsets(partitions, listOffsetsOptions);
                var f = result.partitionResult(tp);
                var info = f.get();
                var offset = info.offset();
                if (offset < last_offset) {
                    log(thread_id, "violation\t" + "listOffset observed offset:" + offset + " after offset:" + last_offset + " was already known");
                }
                update_known_offset(offset);
            } catch (ExecutionException e) {
                var cause = e.getCause();
                if (cause != null) {
                    if (cause instanceof TimeoutException) {
                        timedout_writes++;
                        continue;
                    } else if (cause instanceof NotLeaderOrFollowerException) {
                        failed_writes++;
                        continue;
                    }
                }
                System.out.println(e);
                e.printStackTrace();
                failed_writes++;
            } catch (Exception e) {
                System.out.println(e);
                e.printStackTrace();
                failed_writes++;
            }
        }

        if (client != null) {
            client.close();
        }
    }
}
