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
import java.util.LinkedList;
import java.util.Queue;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import java.time.Duration;
import java.util.concurrent.Semaphore;
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import java.util.Map;
import java.util.Set;
import java.util.HashSet;
import java.util.Collection;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.CommonClientConfigs;

// consistency:
//  - for each workload:
//    - produced on this node is in the output
//  - final check: read data by any node match

public class Workload {
    private static class TrackingRebalanceListener implements ConsumerRebalanceListener {
        public final Consumer<String, String> consumer;
        public final String brokers;
        public final String source;
        public final String group_id;
        public final Workload workload;
        public final int sid;
        public final Map<Integer, Producer<String, String>> producers;
        public final Set<Integer> tracked;
        public boolean reset_requested = false;

        public TrackingRebalanceListener(Workload workload, int sid, Consumer<String, String> consumer, String brokers, String source, String group_id) {
            this.workload = workload;
            this.sid = sid;
            this.consumer = consumer;
            this.brokers = brokers;
            this.source = source;
            this.group_id = group_id;
            this.producers = new HashMap<>();
            this.tracked = new HashSet<>();
        }

        public void close() {
            for (var producer : producers.values()) {
                try {
                    producer.close();
                } catch(Exception e) { }
            }
        }
        
        @Override
        public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
            for (var tp : partitions) {
                try {
                    workload.log(sid, "log\trevoke\t" + tp.partition());
                } catch (Exception e1) {}
                if (tp.topic().equals(source)) {
                    this.tracked.remove(tp.partition());
                }
            }
        }
 
        @Override
        public void onPartitionsLost(Collection<TopicPartition> partitions) {
            for (var tp : partitions) {
                try {
                    workload.log(sid, "log\tlost\t" + tp.partition());
                } catch (Exception e1) {}
                if (tp.topic().equals(source)) {
                    this.tracked.remove(tp.partition());
                }
            }
        }

        private void createProducer(int partition) {
            Producer<String, String> producer = null;
            
            if (producers.containsKey(partition)) {
                producer = producers.get(partition);
                try {
                    producer.close();
                } catch (Exception e1) {}
                producers.remove(partition);
                producer = null;
            }
            
            Properties props = new Properties();
            props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, brokers);
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
            props.put(ProducerConfig.RETRIES_CONFIG, 5);
            props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
            props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "tx-consume-" + source + "-partition-" + partition);

            producer =  new KafkaProducer<>(props);
            producer.initTransactions();
            producers.put(partition, producer);
        }

        @Override
        public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
            for (var tp : partitions) {
                try {
                    workload.log(sid, "log\tassigned\t" + tp.partition());
                } catch (Exception e1) {}
                if (!tp.topic().equals(source)) {
                    continue;
                }
                try {
                    // initializing new txn client to force finish previous
                    // ongoing transactions
                    createProducer(tp.partition());
                    tracked.add(tp.partition());
                } catch (Exception e1) {
                    System.out.println("=== error on onPartitionsAssigned: KafkaProducer::ctor");
                    System.out.println(e1);
                    e1.printStackTrace();

                    reset_requested = true;
                    return;
                }
            }
            
            // onPartitionsAssigned is called after the offsets are set, see kafka doc
            // https://kafka.apache.org/24/javadoc/org/apache/kafka/clients/consumer/ConsumerRebalanceListener.html
            // in case of externally managed offsets they suggest to seek inside
            // onPartitionsAssigned, so the set offsets may come from before the previous
            // tx is committed; setting offset manuattly after we force committed the
            // transacitons above

            AdminClient client = null;
            try {
                Properties props = new Properties();
                props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, brokers);
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

                client = AdminClient.create(props);
                var result = client.listConsumerGroupOffsets(group_id);
                var offsets = result.partitionsToOffsetAndMetadata().get();

                for (var tp : partitions) {
                    if (!tp.topic().equals(source)) {
                        continue;
                    }
                    if (!offsets.containsKey(tp)) {
                        continue;
                    }
                    consumer.seek(tp, offsets.get(tp).offset());
                }
            } catch(Exception e1) {
                System.out.println("=== error on AdminClient::listConsumerGroupOffsets");
                System.out.println(e1);
                e1.printStackTrace();
                reset_requested = true;
            }

            if (client != null) {
                try {
                    client.close();
                } catch (Exception e1) {}
            }
        }
    }
    
    static enum OpProduceStatus {
        WRITING, UNKNOWN, WRITTEN, SKIPPED, SEEN
    }

    static class OpProduceRecord {
        public long oid;
        public int partition;
        public OpProduceStatus status;
    }
    
    public volatile boolean is_active = false;
    public volatile boolean is_paused = false;
    
    private volatile App.InitBody args;
    private BufferedWriter opslog;

    private HashMap<Integer, App.OpsInfo> ops_info;
    private synchronized void succeeded(int thread_id) {
        ops_info.get(thread_id).succeeded_ops += 1;
    }
    private synchronized void timedout(int thread_id) {
        ops_info.get(thread_id).timedout_ops += 1;
    }
    private synchronized void failed(int thread_id) {
        ops_info.get(thread_id).failed_ops += 1;
    }

    private HashMap<Integer, Boolean> should_reset;
    private HashMap<Integer, Long> last_success_us;
    private synchronized void progress(int thread_id) {
        last_success_us.put(thread_id, System.nanoTime() / 1000);
    }
    private synchronized void tick(int thread_id) {
        var now_us = Math.max(last_success_us.get(thread_id), System.nanoTime() / 1000);
        if (now_us - last_success_us.get(thread_id) > 10 * 1000 * 1000) {
            should_reset.put(thread_id, true);
            last_success_us.put(thread_id, now_us);
        }
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
    private synchronized void violation(int thread_id, String message) throws Exception {
        var now_us = System.nanoTime() / 1000;
        if (now_us < past_us) {
            throw new Exception("Time cant go back, observed: " + now_us + " after: " + past_us);
        }
        opslog.write("" + thread_id +
                        "\t" + (now_us - past_us) +
                        "\tviolation" +
                        "\t" + message + "\n");
        opslog.flush();
        opslog.close();
        System.exit(1);
        past_us = now_us;
    }
    public void event(String name) throws Exception {
        log(-1, "event\t" + name);
    }

    private long last_op_id = 0;
    private synchronized long get_op_id() {
        return ++this.last_op_id;
    }

    HashMap<Integer, Semaphore> produce_limiter;
    volatile ArrayList<Thread> producing_threads;
    volatile Thread streaming_thread = null;
    volatile Thread consuming_thread = null;

    private HashMap<Long, OpProduceRecord> producing_records;
    private HashMap<Integer, Queue<Long>> producing_oids;


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
        
        should_reset = new HashMap<>();
        last_success_us = new HashMap<>();
        ops_info = new HashMap<>();
        produce_limiter = new HashMap<>();

        producing_records = new HashMap<>();
        producing_oids = new HashMap<>();
        producing_threads = new ArrayList<>();
        int thread_id=0;

        for (int i=0;i<args.partitions;i++) {
            produce_limiter.put(i, new Semaphore(10));
            final int j = i;
            producing_oids.put(j, new LinkedList<>());
            final var pid=thread_id++;
            last_success_us.put(pid, -1L);
            should_reset.put(pid, false);
            producing_threads.add(new Thread(() -> { 
                try {
                    producingProcess(pid, j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                    System.exit(1);
                }
            }));
        }

        {
            final var sid=thread_id++;
            ops_info.put(sid, new App.OpsInfo());
            last_success_us.put(sid, -1L);
            should_reset.put(sid, false);
            streaming_thread = new Thread(() -> { 
                try {
                    streamingProcess(sid);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                    System.exit(1);
                }
            });
        }

        {
            final var rid=thread_id++;
            last_success_us.put(rid, -1L);
            should_reset.put(rid, false);
            consuming_thread = new Thread(() -> { 
                try {
                    consumingProcess(rid);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                    System.exit(1);
                }
            });
        }

        for (var th : producing_threads) {
            th.start();
        }

        streaming_thread.start();
        consuming_thread.start();
    }

    public void stop() throws Exception {
        is_active = false;
        is_paused = false;
        synchronized(this) {
            this.notifyAll();
        }

        Thread.sleep(1000);
        if (opslog != null) {
            opslog.flush();
        }
        
        System.out.println("waiting for streaming_thread");
        if (streaming_thread != null) {
            streaming_thread.join();
        }

        System.out.println("waiting for consuming_thread");
        if (consuming_thread != null) {
            consuming_thread.join();
        }
        
        for (int i=0;i<args.partitions;i++) {
            produce_limiter.get(i).release(100);
        }
        System.out.println("waiting for producing_threads");
        for (var th : producing_threads) {
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

    private void producingProcess(int pid, int partition) throws Exception {
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
        props.put(ProducerConfig.RETRIES_CONFIG, 5);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "tx-produce-" + args.source + "-partition-" + partition);

        log(pid, "started\t" + args.server + "\tproducing\t" + partition);
    
        Producer<String, String> producer = null;

        while (is_active) {
            tick(pid);

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
                    producer.initTransactions();
                    log(pid, "constructed");
                    continue;
                }
            } catch (Exception e1) {
                log(pid, "err");
                System.out.println("=== error on KafkaProducer ctor");
                System.out.println(e1);
                e1.printStackTrace();
                try {
                    if (producer != null) {
                        producer.close();
                    }
                } catch(Exception e2) { }
                producer = null;
                continue;
            }

            long offset = -1;

            var op = new OpProduceRecord();
            op.oid = get_op_id();
            op.partition = partition;
            op.status = OpProduceStatus.WRITING;

            synchronized(this) {
                producing_records.put(op.oid, op);
                producing_oids.get(partition).add(op.oid);
            }

            try {
                log(pid, "send\t" + op.oid);
                producer.beginTransaction();
                offset = producer.send(new ProducerRecord<String, String>(args.source, partition, args.server, "" + op.oid)).get().offset();
                producer.commitTransaction();
            } catch (Exception e1) {
                synchronized(this) {
                    if (op.status == OpProduceStatus.SEEN) {
                        producing_records.remove(op.oid);
                    }
                    if (op.status == OpProduceStatus.SKIPPED) {
                        producing_records.remove(op.oid);
                    }
                    op.status = OpProduceStatus.UNKNOWN;
                }

                log(pid, "err");
                System.out.println("=== error on send");
                System.out.println(e1);
                e1.printStackTrace();
                try {
                    producer.close();
                } catch (Exception e3) {}
                producer = null;
    
                continue;
            }

            synchronized(this) {
                if (op.status == OpProduceStatus.SEEN) {
                    producing_records.remove(op.oid);
                }
                if (op.status == OpProduceStatus.SKIPPED) {
                    violation(pid, "written message can't be skipped oid:" + op.oid);
                }
                op.status = OpProduceStatus.WRITTEN;
            }

            progress(pid);

            log(pid, "ok\t" + offset);

            produce_limiter.get(partition).acquire();
        }
    
        if (producer != null) {
            try {
                producer.close();
            } catch (Exception e) { }
        }
    }

    private void streamingProcess(int sid) throws Exception {
        Properties cprops = new Properties();
        cprops.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, args.brokers);
        cprops.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        cprops.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        cprops.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        cprops.put(ConsumerConfig.GROUP_ID_CONFIG, args.group_id);
        cprops.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 10000);
        cprops.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 3000);
        // default value: 540000
        cprops.put(ConsumerConfig.CONNECTIONS_MAX_IDLE_MS_CONFIG, 60000);
        // default value: 60000
        cprops.put(ConsumerConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, 10000);
        // default value: 500
        cprops.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 500);
        // default value: 300000
        cprops.put(ConsumerConfig.METADATA_MAX_AGE_CONFIG, 10000);
        // default value: 1000
        cprops.put(ConsumerConfig.RECONNECT_BACKOFF_MAX_MS_CONFIG, 1000);
        // default value: 50
        cprops.put(ConsumerConfig.RECONNECT_BACKOFF_MS_CONFIG, 50);
        // defaut value: 30000
        cprops.put(ConsumerConfig.REQUEST_TIMEOUT_MS_CONFIG, 10000);
        // default value: 100
        cprops.put(ConsumerConfig.RETRY_BACKOFF_MS_CONFIG, 100);
        cprops.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            "org.apache.kafka.common.serialization.StringDeserializer");
        cprops.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            "org.apache.kafka.common.serialization.StringDeserializer");
        
        log(sid, "started\t" + args.server + "\tstreaming");

        Consumer<String, String> consumer = null;
        TrackingRebalanceListener tracker = null;
        while (is_active) {
            tick(sid);

            synchronized(this) {
                if (should_reset.get(sid)) {
                    should_reset.put(sid, false);

                    if (consumer != null) {
                        try {
                            consumer.close();
                        } catch(Exception e) {}
                        consumer = null;
                    }

                    if (tracker != null) {
                        try {
                            tracker.close();
                        } catch(Exception e) {}
                        tracker = null;
                    }
                }

                if (is_paused) {
                    if (consumer != null) {
                        try {
                            consumer.close();
                        } catch(Exception e) {}
                        consumer = null;
                    }

                    if (tracker != null) {
                        try {
                            tracker.close();
                        } catch(Exception e) {}
                        tracker = null;
                    }

                    while (is_paused) {
                        try {
                            this.wait();
                        } catch (Exception e) { }
                    }
                }
            }

            try {
                if (consumer == null) {
                    log(sid, "constructing\tstreaming");
                    consumer = new KafkaConsumer<>(cprops);
                    tracker = new TrackingRebalanceListener(this, sid, consumer, args.brokers, args.source, args.group_id);
                    consumer.subscribe(Collections.singleton(args.source), tracker);
                    log(sid, "constructed");
                }
            } catch (Exception e1) {
                log(sid, "err");
                System.out.println("=== error on KafkaConsumer ctor");
                System.out.println(e1);
                e1.printStackTrace();

                if (consumer != null) {
                    try {
                        consumer.close();
                    } catch (Exception e2) {}
                    consumer = null;
                    tracker = null;
                }
                continue;
            }

            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(10000));
            var it = records.iterator();
            while (it.hasNext()) {
                var record = it.next();

                if (tracker.reset_requested) {
                    if (consumer != null) {
                        try {
                            consumer.close();
                        } catch (Exception e2) {}
                        consumer = null;
                        tracker = null;
                    }
                    break;
                }

                log(sid, "read\t" + record.key() + "\t" + record.partition() + "\t" + record.value());

                if (!tracker.tracked.contains(record.partition())) {
                    violation(sid, "partition " + record.partition() + " isn't tracked");
                }

                var producer = tracker.producers.get(record.partition());
                
                try {
                    log(sid, "tx");
                    producer.beginTransaction();
                    producer.send(new ProducerRecord<String, String>(args.target, args.server, "" + record.key() + "\t" + record.partition() + "\t" + record.value()));
                    var offsets = new HashMap<TopicPartition, OffsetAndMetadata>();
                    offsets.put(new TopicPartition(args.source, record.partition()), new OffsetAndMetadata(record.offset() + 1));
                    producer.sendOffsetsToTransaction(offsets, args.group_id);
                } catch (Exception e1) {
                    System.out.println("=== error on send or sendOffsetsToTransaction");
                    System.out.println(e1);
                    e1.printStackTrace();

                    try {
                        log(sid, "brt");
                        producer.abortTransaction();
                        log(sid, "ok");
                        failed(sid);
                    } catch (Exception e2) {
                        log(sid, "err");
                        System.out.println("=== error on abort");
                        System.out.println(e2);
                        e2.printStackTrace();
                    }

                    tracker.reset_requested = true;

                    continue;
                }
                
                try {
                    log(sid, "cmt");
                    producer.commitTransaction();
                    log(sid, "ok");
                    succeeded(sid);
                    progress(sid);
                    produce_limiter.get(record.partition()).release();
                } catch (Exception e1) {
                    log(sid, "err");
                    failed(sid);
                    System.out.println("=== error on commit");
                    System.out.println(e1);
                    e1.printStackTrace();
                    tracker.reset_requested = true;
                }
            }
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
            tick(rid);

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
                progress(rid);
                var record = it.next();

                long offset = record.offset();
                var parts = record.value().split("\t");
                String server = parts[0];
                int partition = Integer.parseInt(parts[1]);
                long oid = Long.parseLong(parts[2]);

                if (offset <= prev_offset) {
                    violation(rid, "reads must be monotonic but observed " + offset + " after " + prev_offset);
                }
                prev_offset = offset;

                log(rid, "seen\t" + record.offset() + "\t" + record.key() + "\t" + server + "\t" + partition + "\t" + oid);

                if (!server.equals(args.server)) {
                    continue;
                }

                synchronized (this) {
                    if (!producing_records.containsKey(oid)) {
                        violation(rid, "read an unknown oid:" + oid);
                    }
                    var op = producing_records.get(oid);
                    if (op.status == OpProduceStatus.SEEN) {
                        violation(rid, "can't read an already seen oid:" + oid);
                    }
                    if (op.status == OpProduceStatus.SKIPPED) {
                        violation(rid, "can't read an already skipped oid:" + oid);
                    }
                    var oids = producing_oids.get(partition);
                    
                    while (oids.size() > 0 && oids.element() < oid) {
                        var prev_oid = oids.remove();
                        var prev_op = producing_records.get(prev_oid);
                        if (prev_op.status == OpProduceStatus.SEEN) {
                            violation(rid, "skipped op is already seen:" + prev_oid);
                        }
                        if (prev_op.status == OpProduceStatus.SKIPPED) {
                            violation(rid, "skipped op is already skipped:" + prev_oid);
                        }
                        if (prev_op.status == OpProduceStatus.WRITTEN) {
                            violation(rid, "skipped op is already acked:" + prev_oid);
                        }
                        if (prev_op.status == OpProduceStatus.WRITING) {
                            prev_op.status = OpProduceStatus.SKIPPED;
                        }
                        if (prev_op.status == OpProduceStatus.UNKNOWN) {
                            producing_records.remove(prev_oid);
                        }
                    }

                    if (oids.size()==0) {
                        violation(rid, "attempted writes should include seen oid:" + oid);
                    }
                    if (oids.element() != oid) {
                        violation(rid, "attempted writes should include seen oid:" + oid);
                    }

                    oids.remove();

                    if (op.status == OpProduceStatus.WRITING) {
                        op.status = OpProduceStatus.SEEN;
                    } else if (op.status == OpProduceStatus.WRITTEN) {
                        producing_records.remove(oid);
                    } else if (op.status == OpProduceStatus.UNKNOWN) {
                        producing_records.remove(oid);
                    } else {
                        violation(rid, "unknown status: " + op.status.name());
                    }
                }
            }
        }
    }
}