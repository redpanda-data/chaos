package io.vectorized;
import java.io.*;
import java.util.Properties;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import java.util.Random;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.lang.Thread;
import org.apache.kafka.common.errors.TimeoutException;
import org.apache.kafka.common.KafkaException;
import java.io.BufferedWriter;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.HashMap;

public class Workload {
    public volatile boolean is_active = false;
    
    private volatile App.InitBody args;
    private volatile ArrayList<Thread> threads;
    private BufferedWriter opslog;
    private long past_us;
    private long before_us = -1;
    private long last_op = 0;
    private Random random;

    private long last_success_us = -1;
    private boolean should_reset;
    private HashMap<Integer, App.OpsInfo> ops_info;

    Producer<String, String> producer = null;

    synchronized long get_op() {
        return ++this.last_op;
    }

    private synchronized void tick() {
        var now_us = Math.max(last_success_us, System.nanoTime() / 1000);
        if (now_us - last_success_us > 10000*1000) {
            should_reset = true;
            last_success_us = now_us;
        }
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
        opslog = new BufferedWriter(new FileWriter(new File(new File(args.experiment, args.server), "workload.log")));
        
        should_reset = false;
        ops_info = new HashMap<>();
        random = new Random();

        threads = new ArrayList<>();
        for (int i=0;i<this.args.settings.concurrency;i++) {
            final var j=i;
            ops_info.put(j, new App.OpsInfo());
            threads.add(new Thread(() -> { 
                try {
                    process(j);
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

        Thread.sleep(1000);
        if (opslog != null) {
            opslog.flush();
        }
        
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

    private synchronized void succeeded(int thread_id) {
        ops_info.get(thread_id).succeeded_ops += 1;
        last_success_us = Math.max(last_success_us, System.nanoTime() / 1000);
    }
    private synchronized void timedout(int thread_id) {
        ops_info.get(thread_id).timedout_ops += 1;
    }
    private synchronized void failed(int thread_id) {
        ops_info.get(thread_id).failed_ops += 1;
    }

    public synchronized HashMap<String, App.OpsInfo> get_ops_info() {
        HashMap<String, App.OpsInfo> result = new HashMap<>();
        for (Integer key : ops_info.keySet()) {
            result.put("" + key, ops_info.get(key).copy());
        }
        return result;
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
        // default value: 16384
        props.put(ProducerConfig.BATCH_SIZE_CONFIG, 0);
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
        props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        props.put(ProducerConfig.RETRIES_CONFIG, args.settings.retries);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, args.settings.enable_idempotency);

        log(thread_id, "started\t" + args.server);

        boolean was_constructed = false;

        while (is_active) {
            tick();

            long op = get_op();
            Future<RecordMetadata> f;

            if (args.settings.jitter_ms > 0) {
                Thread.sleep(random.nextInt(args.settings.jitter_ms));
            }

            synchronized(this) {
                if (should_reset) {
                    should_reset = false;
                    if (producer != null) {
                        try {
                            producer.close();
                            producer = null;
                        } catch(Exception e) {}
                    }
                }
                try {
                    if (producer == null) {
                        log(thread_id, "constructing");
                        producer = new KafkaProducer<>(props);
                        log(thread_id, "constructed");
                        was_constructed = true;
                        continue;
                    }
                } catch (Exception e) {
                    log(thread_id, "err");
                    System.out.println(e);
                    e.printStackTrace();
                    failed(thread_id);
                    continue;
                }

                if (!was_constructed) {
                    log(thread_id, "constructing");
                    log(thread_id, "constructed");
                    was_constructed = true;
                }
                log(thread_id, "msg\t" + op);
                f = producer.send(new ProducerRecord<String, String>(args.topic, args.server, "" + op));
            }

            try {
                var m = f.get();
                succeeded(thread_id);
                log(thread_id, "ok\t" + m.offset());
            } catch (ExecutionException e) {
                var cause = e.getCause();
                if (cause != null) {
                    if (cause instanceof TimeoutException) {
                        log(thread_id, "time");
                        timedout(thread_id);
                        continue;
                    } else if (cause instanceof KafkaException) {
                        log(thread_id, "err");
                        failed(thread_id);
                        System.out.println(e);
                        e.printStackTrace();
                        synchronized(this) {
                            should_reset = true;
                        }
                        continue;
                    }
                }
 
                log(thread_id, "err");
                System.out.println(e);
                failed(thread_id);
            } catch (Exception e) {
                log(thread_id, "err");
                System.out.println(e);
                e.printStackTrace();
                failed(thread_id);
            }
        }
        
        synchronized (this) {
            if (producer != null) {
                try {
                    producer.close();
                    producer = null;
                } catch(Exception e) {}
            }
        }
    }
}
