package io.vectorized;
import java.io.*;
import java.util.Properties;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import java.lang.Thread;
import java.io.BufferedWriter;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Collections;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import java.time.Duration;
import java.util.Random;
import java.util.concurrent.Semaphore;

public class Workload {
    public volatile boolean is_active = false;
    
    private volatile App.InitBody args;
    private BufferedWriter opslog;

    private HashMap<Integer, App.OpsInfo> ops_info;
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

    private long last_success_us = -1;
    private HashMap<Integer, Boolean> should_reset;
    private synchronized void tick() {
        var now_us = Math.max(last_success_us, System.nanoTime() / 1000);
        if (now_us - last_success_us > 10 * 1000 * 1000) {
            for (var thread_id : should_reset.keySet()) {
                should_reset.put(thread_id, true);
            }
            last_success_us = now_us;
        }
    }

    private long last_op_id = 0;
    private synchronized long get_op_id() {
        return ++this.last_op_id;
    }

    private long past_us;
    private synchronized void log(int thread_id, String message) throws Exception {
        var now_us = System.nanoTime() / 1000;
        if (now_us < past_us) {
            throw new Exception("Time cant go back, observed: " + now_us + " after: " + past_us);
        }
        opslog.write("" + thread_id +
                        "\t" + (now_us - past_us) +
                        "\t" + message + "\n");
        past_us = now_us;
    }
    public void event(String name) throws Exception {
        log(-1, "event\t" + name);
    }

    private volatile ArrayList<Thread> threads;
    private volatile Random random;
    private Semaphore produce_gauge;

    public Workload(App.InitBody args) {
        this.args = args;
        this.random = new Random();
    }

    public void start() throws Exception {
        File root = new File(args.experiment, args.server);

        if (!root.mkdir()) {
            throw new Exception("Can't create folder: " + root);
        }

        is_active = true;
        past_us = 0;
        opslog = new BufferedWriter(new FileWriter(new File(new File(args.experiment, args.server), "workload.log")));
        
        should_reset = new HashMap<>();
        ops_info = new HashMap<>();

        int thread_id=0;
        threads = new ArrayList<>();

        produce_gauge = new Semaphore(200);
        
        {
            final var j=thread_id++;
            should_reset.put(j, false);
            ops_info.put(j, new App.OpsInfo());
            threads.add(new Thread(() -> { 
                try {
                    producingProcess(j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                    try {
                        opslog.flush();
                        opslog.close();
                    } catch(Exception e2) {}
                    System.exit(1);
                }
            }));
        }

        {
            final var j=thread_id++;
            should_reset.put(j, false);
            ops_info.put(j, new App.OpsInfo());
            threads.add(new Thread(() -> { 
                try {
                    streamingProcess(j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                    try {
                        opslog.flush();
                        opslog.close();
                    } catch(Exception e2) {}
                    System.exit(1);
                }
            }));
        }

        {
            final var j=thread_id++;
            should_reset.put(j, false);
            ops_info.put(j, new App.OpsInfo());
            threads.add(new Thread(() -> { 
                try {
                    consumingProcess(j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                    try {
                        opslog.flush();
                        opslog.close();
                    } catch(Exception e2) {}
                    System.exit(1);
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

    public synchronized HashMap<String, App.OpsInfo> get_ops_info() {
        HashMap<String, App.OpsInfo> result = new HashMap<>();
        for (Integer key : ops_info.keySet()) {
            result.put("" + key, ops_info.get(key).copy());
        }
        return result;
    }

    private void producingProcess(int pid) throws Exception {
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
        
        props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        props.put(ProducerConfig.RETRIES_CONFIG, args.settings.retries);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
    
    
        Producer<String, String> producer = null;
    
        log(pid, "started\t" + args.server + "\tproducing");
    
        while (is_active) {
            tick();

            produce_gauge.acquire();
    
            synchronized(this) {
                if (should_reset.get(pid)) {
                    should_reset.put(pid, false);
                    if (producer != null) {
                        try {
                            producer.close();
                        } catch(Exception e) {}
                        producer = null;
                    }
                }
            }
    
            try {
                if (producer == null) {
                    log(pid, "constructing");
                    producer = new KafkaProducer<>(props);
                    log(pid, "constructed");
                    continue;
                }
            } catch (Exception e1) {
                log(pid, "err");
                System.out.println(e1);
                e1.printStackTrace();
                failed(pid);
                try {
                    if (producer != null) {
                        producer.close();
                    }
                } catch(Exception e2) { }
                producer = null;
                continue;
            }

            var oid = get_op_id();
    
            log(pid, "writing\t" + oid);

            long offset = -1;

            try {
                var f1 = producer.send(new ProducerRecord<String, String>(args.source, args.server, "" + oid));
                offset = f1.get().offset();
            } catch (Exception e1) {
                System.out.println("error on send");
                e1.printStackTrace();
                log(pid, "err");
                try {
                    producer.close();
                } catch (Exception e3) {}
                producer = null;
    
                continue;
            }
    
            log(pid, "ok\t" + offset);
            succeeded(pid);
        }
    
        if (producer != null) {
            try {
                producer.close();
            } catch (Exception e) { }
        }
    }

    private void streamingProcess(int sid) throws Exception {
        Properties pprops = new Properties();
        pprops.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, args.brokers);
        pprops.put(ProducerConfig.ACKS_CONFIG, "all");
        pprops.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, "org.apache.kafka.common.serialization.StringSerializer");
        pprops.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, "org.apache.kafka.common.serialization.StringSerializer");

        // default value: 600000
        pprops.put(ProducerConfig.CONNECTIONS_MAX_IDLE_MS_CONFIG, 60000);
        // default value: 120000
        pprops.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 10000);
        // default value: 0
        pprops.put(ProducerConfig.LINGER_MS_CONFIG, 0);
        // default value: 60000
        pprops.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, 10000);
        // default value: 1000
        pprops.put(ProducerConfig.RECONNECT_BACKOFF_MAX_MS_CONFIG, 1000);
        // default value: 50
        pprops.put(ProducerConfig.RECONNECT_BACKOFF_MS_CONFIG, 50);
        // default value: 30000
        pprops.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000);
        // default value: 100
        pprops.put(ProducerConfig.RETRY_BACKOFF_MS_CONFIG, 100);
        // default value: 300000
        pprops.put(ProducerConfig.METADATA_MAX_AGE_CONFIG, 10000);
        // default value: 300000
        pprops.put(ProducerConfig.METADATA_MAX_IDLE_CONFIG, 10000);

        pprops.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        pprops.put(ProducerConfig.RETRIES_CONFIG, args.settings.retries);
        pprops.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        pprops.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "tx-" + sid);

        Properties cprops = new Properties();
        cprops.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, args.brokers);
        cprops.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        cprops.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        cprops.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        cprops.put(ConsumerConfig.GROUP_ID_CONFIG, args.group_id);
        cprops.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            "org.apache.kafka.common.serialization.StringDeserializer");
        cprops.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            "org.apache.kafka.common.serialization.StringDeserializer");

        log(sid, "started\t" + args.server + "\tstreaming");

        Producer<String, String> producer = null;
        Consumer<String, String> consumer = null;
        var source_tp = new TopicPartition(args.source, 0);

        while (is_active) {
            tick();
    
            synchronized(this) {
                if (should_reset.get(sid)) {
                    should_reset.put(sid, false);
                    if (producer != null) {
                        try {
                            producer.close();
                        } catch(Exception e) {}
                        producer = null;
                    }

                    if (consumer != null) {
                        try {
                            consumer.close();
                        } catch(Exception e) {}
                        consumer = null;
                    }
                }
            }

            try {
                if (producer == null) {
                    if (consumer != null) {
                        try {
                            consumer.close();
                        } catch(Exception e) {}
                        consumer = null;
                    }

                    log(sid, "constructing");
                    producer = new KafkaProducer<>(pprops);
                    producer.initTransactions();
                    consumer = new KafkaConsumer<>(cprops);
                    consumer.subscribe(Collections.singleton(args.source));
                    log(sid, "constructed");
                    continue;
                }
            } catch (Exception e1) {
                log(sid, "err");
                System.out.println(e1);
                e1.printStackTrace();
                failed(sid);
                try {
                    if (producer != null) {
                        producer.close();
                    }
                } catch(Exception e2) { }
                producer = null;
                if (consumer != null) {
                    try {
                        consumer.close();
                    } catch(Exception e2) {}
                    consumer = null;
                }
                continue;
            }

            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(10000));
            var it = records.iterator();
            while (it.hasNext()) {
                var record = it.next();
                if (!record.key().equals(args.server)) {
                    continue;
                }

                long offset = record.offset();
                long oid = Long.parseLong(record.value());

                log(sid, "tx");
                producer.beginTransaction();
                try {
                    producer.send(new ProducerRecord<String, String>(args.target, args.server, "" + oid));
                    var offsets = new HashMap<TopicPartition, OffsetAndMetadata>();
                    offsets.put(source_tp, new OffsetAndMetadata(offset + 1));
                    producer.sendOffsetsToTransaction(offsets, args.group_id);
                } catch (Exception e1) {
                    System.out.println("error on produce => aborting tx");
                    System.out.println(e1);
                    e1.printStackTrace();
        
                    try {
                        log(sid, "brt");
                        producer.abortTransaction();
                        log(sid, "ok");
                        failed(sid);
                    } catch (Exception e2) {
                        System.out.println("error on abort => reset producer");
                        System.out.println(e2);
                        e2.printStackTrace();
                        log(sid, "err");
                    }

                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;

                    try {
                        consumer.close();
                    } catch (Exception e3) {}
                    consumer = null;

                    break;
                }

                try {
                    log(sid, "cmt");
                    producer.commitTransaction();
                    produce_gauge.release();
                    log(sid, "ok");
                    succeeded(sid);
                } catch (Exception e1) {
                    System.out.println("error on commit => reset producer");
                    System.out.println(e1);
                    e1.printStackTrace();
                    log(sid, "err");
                    failed(sid);
                    
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;

                    try {
                        consumer.close();
                    } catch (Exception e3) {}
                    consumer = null;

                    break;
                }
            }
        }

        if (producer != null) {
            try {
                producer.close();
            } catch (Exception e) { }
        }

        if (consumer != null) {
            try {
                consumer.close();
            } catch (Exception e) { }
        }
    }

    private void consumingProcess(int rid) throws Exception {
        var tp = new TopicPartition(args.target, 0);
        var tps = Collections.singletonList(tp);
        
        Properties props = new Properties();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, args.brokers);
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            "org.apache.kafka.common.serialization.StringDeserializer");
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            "org.apache.kafka.common.serialization.StringDeserializer");
        // default value: 540000
        props.put(ConsumerConfig.CONNECTIONS_MAX_IDLE_MS_CONFIG, 60000);
        // default value: 60000
        props.put(ConsumerConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, 10000);
        // default value: 500
        props.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 500);
        // default value: 300000
        props.put(ConsumerConfig.METADATA_MAX_AGE_CONFIG, 10000);
        // default value: 1000
        props.put(ConsumerConfig.RECONNECT_BACKOFF_MAX_MS_CONFIG, 1000);
        // default value: 50
        props.put(ConsumerConfig.RECONNECT_BACKOFF_MS_CONFIG, 50);
        // defaut value: 30000
        props.put(ConsumerConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000);
        // default value: 100
        props.put(ConsumerConfig.RETRY_BACKOFF_MS_CONFIG, 100);

        KafkaConsumer<String, String> consumer = null;
        
        log(rid, "started\t" + args.server + "\tconsuming");

        long prev_offset = -1;

        while (is_active) {
            tick();

            synchronized(this) {
                if (should_reset.get(rid)) {
                    should_reset.put(rid, false);
                    consumer = null;
                }
            }

            try {
                if (consumer == null) {
                    log(rid, "constructing");
                    consumer = new KafkaConsumer<>(props);
                    consumer.assign(tps);
                    if (prev_offset == -1) {
                        consumer.seekToBeginning(tps);
                    } else {
                        consumer.seek(tp, prev_offset+1);
                    }
                    log(rid, "constructed");
                    continue;
                }
            } catch (Exception e) {
                log(rid, "err");
                System.out.println(e);
                e.printStackTrace();
                failed(rid);
                continue;
            }

            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(10000));
            var it = records.iterator();
            while (it.hasNext()) {
                var record = it.next();

                if (!record.key().equals(args.server)) {
                    continue;
                }

                long offset = record.offset();
                long oid = Long.parseLong(record.value());
            }
        }
    }
}