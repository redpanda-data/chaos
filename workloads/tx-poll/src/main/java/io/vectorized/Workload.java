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
import org.apache.kafka.clients.consumer.ConsumerRebalanceListener;
import java.util.HashSet;
import java.util.Collection;
import java.util.Random;

import org.apache.kafka.common.errors.ProducerFencedException;
import org.apache.kafka.common.errors.OutOfOrderSequenceException;
import org.apache.kafka.common.errors.AuthorizationException;
import org.apache.kafka.common.errors.InterruptException;
import org.apache.kafka.common.errors.TimeoutException;

public class Workload {
    private static class TrackingRebalanceListener implements ConsumerRebalanceListener {
        public final HashSet<Integer> tracked_partitions = new HashSet<>();
        public long version = 0;
        public final Workload workload;
        public final int pid;

        public TrackingRebalanceListener(Workload workload, int pid) {
            this.workload = workload;
            this.pid = pid;
        }

        @Override
        public void onPartitionsRevoked(Collection<TopicPartition> partitions) {
            for (var tp : partitions) {
                try {
                    workload.log(pid, "log\trevoked\t" + tp.partition());
                } catch (Exception e1) {}
                this.tracked_partitions.remove(tp.partition());
            }
            this.version++;
        }
 
        @Override
        public void onPartitionsLost(Collection<TopicPartition> partitions) {
            for (var tp : partitions) {
                try {
                    workload.log(pid, "log\tlost\t" + tp.partition());
                } catch (Exception e1) {}
                this.tracked_partitions.remove(tp.partition());
            }
            this.version++;
        }

        @Override
        public void onPartitionsAssigned(Collection<TopicPartition> partitions) {
            for (var tp : partitions) {
                try {
                    workload.log(pid, "log\tassigned\t" + tp.partition());
                } catch (Exception e1) {}
                this.tracked_partitions.add(tp.partition());
            }
            this.version++;
        }
    }

    static enum TaskType {
        PRODUCE, CONSUME, NONE, SUBSCRIBE
    }

    static class Log {
        public String topic;
        public int partition;
    }

    static class Task {
        public TaskType type;
        public ArrayList<Log> logs;
        public ArrayList<String> topics;
    }

    public volatile boolean is_active = false;
    
    private volatile App.InitBody args;
    private BufferedWriter opslog;

    private HashMap<Integer, App.OpsInfo> ops_info;
    private synchronized void succeeded(int thread_id) {
        ops_info.get(thread_id).succeeded_ops += 1;
    }
    private synchronized void failed(int thread_id) {
        ops_info.get(thread_id).failed_ops += 1;
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

    private long last_key = 0;
    synchronized String get_key() {
        this.last_key++;
        if (args.settings.key_rank <= 0) {
            return "" + this.last_key;
        }
        return "" + (this.last_key % args.settings.key_rank);
    }

    private HashSet<Integer> subscribed = new HashSet<>();
    private HashSet<Integer> consumer_thread = new HashSet<>();
    private HashSet<Integer> producer_thread = new HashSet<>();
    private long produce_counter = 0;

    private Task getProduceTask(int pid) throws Exception {
        produce_counter++;
        var c = produce_counter % (args.settings.topics * args.settings.partitions);

        Task task = new Task();
        task.topics = new ArrayList<>();
        task.logs = new ArrayList<>();
        task.type = TaskType.PRODUCE;
        Log log = new Log();
        long topic = c / args.settings.partitions;
        int partition = (int)(c % args.settings.partitions);
        log.topic = "topic" + topic;
        log.partition = partition;
        task.logs.add(log);
        log = new Log();
        log.topic = "topic" + random.nextInt(args.settings.topics);
        log.partition = random.nextInt(args.settings.partitions);
        task.logs.add(log);
        return task;
    }

    private Task getSubscribeTask(int pid) throws Exception {
        subscribed.add(pid);
        Task task = new Task();
        task.topics = new ArrayList<>();
        task.logs = new ArrayList<>();
        task.type = TaskType.SUBSCRIBE;
        if (args.settings.topics==0) {
            throw new Exception("number of topics can't be null");
        } else if (args.settings.topics == 1) {
            task.topics.add("topic0");
        } else {
            int topic0 = random.nextInt(args.settings.topics);
            int topic1 = topic0;
            while (topic0 == topic1) {
                topic1 = random.nextInt(args.settings.topics);
            }
            task.topics.add("topic" + topic0);
            task.topics.add("topic" + topic1);
        }
        return task;
    }

    private Task getConsumeTask(int pid) throws Exception {
        if (!subscribed.contains(pid)) {
            return getSubscribeTask(pid);
        }
        Task task = new Task();
        task.topics = new ArrayList<>();
        task.logs = new ArrayList<>();
        task.type = TaskType.CONSUME;
        return task;
    }

    synchronized Task getTask(int pid, TaskType type, boolean failed) throws Exception {
        if (!consumer_thread.contains(pid) && !producer_thread.contains(pid)) {
            if (consumer_thread.size() > producer_thread.size()) {
                producer_thread.add(pid);
            } else {
                consumer_thread.add(pid);
            }
        }

        if (producer_thread.contains(pid)) {
            return getProduceTask(pid);
        }

        if (type == TaskType.NONE) {
            return getProduceTask(pid);
        }

        if (type == TaskType.SUBSCRIBE && failed) {
            subscribed.remove(pid);
            return getSubscribeTask(pid);
        }

        if (random.nextInt(100) < args.settings.subscribe_percent) {
            return getSubscribeTask(pid);
        }

        return getConsumeTask(pid);
    }

    volatile ArrayList<Thread> threads;
    volatile Random random = new Random();


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
        
        ops_info = new HashMap<>();

        threads = new ArrayList<>();
        int thread_id=0;

        for (int i=0;i<args.settings.threads;i++) {
            final var pid=thread_id++;
            ops_info.put(pid, new App.OpsInfo());
            threads.add(new Thread(() -> { 
                try {
                    process(pid);
                } catch(Exception e) {
                    synchronized (this) {
                        System.out.println(e);
                        e.printStackTrace();
                    }
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
        synchronized(this) {
            this.notifyAll();
        }

        Thread.sleep(1000);
        if (opslog != null) {
            opslog.flush();
        }
        
        System.out.println("waiting for producing_threads");
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


    private void process(int pid) throws Exception {
        Properties cprops = new Properties();
        cprops.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, args.brokers);
        cprops.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        cprops.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        cprops.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
        cprops.put(ConsumerConfig.GROUP_ID_CONFIG, args.settings.group_id);
        cprops.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 6000);
        cprops.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 300);
        cprops.put(ConsumerConfig.SOCKET_CONNECTION_SETUP_TIMEOUT_MAX_MS_CONFIG, 1000);
        cprops.put(ConsumerConfig.SOCKET_CONNECTION_SETUP_TIMEOUT_MS_CONFIG, 500);
        
        // default value: 540000
        cprops.put(ConsumerConfig.CONNECTIONS_MAX_IDLE_MS_CONFIG, 60000);
        // default value: 60000
        cprops.put(ConsumerConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, 10000);
        // default value: 500
        cprops.put(ConsumerConfig.FETCH_MAX_WAIT_MS_CONFIG, 500);
        // default value: 300000
        cprops.put(ConsumerConfig.METADATA_MAX_AGE_CONFIG, 60000);
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
        
        Producer<String, String> producer = null;
        Consumer<String, String> consumer = null;
        TrackingRebalanceListener tracker = null;

        log(pid, "started\t" + args.server + "\tthread");

        boolean failed = false;
        Task task = null;
        while (true) {
            try {
                if (producer == null) {
                    log(pid, "constructing.producer");
                    producer = createProducer(pid);
                    log(pid, "constructed.producer");
                    continue;
                }
            } catch (Exception e1) {
                log(pid, "err.producer");
                synchronized (this) {
                    System.out.println("=== error on KafkaProducer ctor pid:" + pid);
                    System.out.println(e1);
                    e1.printStackTrace();
                }
                try {
                    if (producer != null) {
                        producer.close();
                    }
                } catch(Exception e2) { }
                producer = null;
                continue;
            }

            try {
                if (consumer == null) {
                    log(pid, "constructing.consumer");
                    consumer = new KafkaConsumer<>(cprops);
                    log(pid, "constructed.consumer");
                }
            } catch (Exception e1) {
                log(pid, "err.consumer");
                synchronized (this) {
                    System.out.println("=== error on KafkaConsumer ctor");
                    System.out.println(e1);
                    e1.printStackTrace();
                }

                if (consumer != null) {
                    try {
                        consumer.close();
                    } catch (Exception e2) {}
                    consumer = null;
                }
                continue;
            }

            task = getTask(pid, task == null ? TaskType.NONE : task.type, failed);

            if (task.type == TaskType.SUBSCRIBE) {
                try {
                    log(pid, "subscribe");
                    tracker = new TrackingRebalanceListener(this, pid);
                    consumer.subscribe(task.topics, tracker);
                    log(pid, "ok.subscribe");
                    failed = false;
                } catch (Exception e1) {
                    log(pid, "err.subscribe");
                    synchronized (this) {
                        System.out.println("=== error on consumer.subscribe");
                        System.out.println(e1);
                        e1.printStackTrace();
                    }
                    tracker = null;
                    failed = true;
                    continue;
                }
            } else if (task.type == TaskType.PRODUCE) {
                try {
                    log(pid, "produce");
                    producer.beginTransaction();

                    for (int i=0;i < task.logs.size();i++) {
                        var key = get_key();
                        var log = task.logs.get(i);
                        ArrayList<Long> log_ops = new ArrayList<>();
                        for (int j=0;j<5;j++) {
                            log_ops.add(get_op_id());
                        }
                        String send_msg = "send\t" + log.topic + "\t" + log.partition + "\t" + key;
                        for (int j=0;j<log_ops.size();j++) {
                            send_msg += "\t" + log_ops.get(j);
                        }
                        log(pid, send_msg);
                        String offsets_msg = "offsets";
                        for (int j=0;j<log_ops.size();j++) {
                            offsets_msg += "\t" + producer.send(new ProducerRecord<String, String>(log.topic, log.partition, key, "" + log_ops.get(j))).get().offset();
                        }
                        log(pid, offsets_msg);
                    }
                } catch (ProducerFencedException | OutOfOrderSequenceException | AuthorizationException e1) {
                    failed = true;
                    failed(pid);
                    // TODO: mark it is as rejected
                    log(pid, "err.produce");
                    synchronized (this) {
                        System.out.println("=== error on send pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                    continue;
                } catch (Exception e1) {
                    failed(pid);
                    synchronized (this) {
                        System.out.println("=== error on send pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }

                    try {
                        producer.abortTransaction();
                        log(pid, "brt.produce");
                        failed = false;
                    } catch (Exception e2) {
                        failed = true;
                        log(pid, "err.produce");
                        synchronized (this) {
                            System.out.println("=== error on abort pid:" + pid);
                            System.out.println(e2);
                            e2.printStackTrace();
                        }
                        try {
                            producer.close();
                        } catch (Exception e3) {}
                        producer = null;
                    }
                    continue;
                }

                try {
                    producer.commitTransaction();
                    log(pid, "cmt.produce");
                    succeeded(pid);
                    failed = false;
                } catch (ProducerFencedException | OutOfOrderSequenceException | AuthorizationException e1) {
                    failed = true;
                    failed(pid);
                    // TODO: mark it is as rejected
                    log(pid, "err.produce");
                    synchronized (this) {
                        System.out.println("=== error on commit pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                    continue;
                } catch (TimeoutException | InterruptException e1) {
                    failed = true;
                    failed(pid);
                    log(pid, "err.produce");
                    synchronized (this) {
                        System.out.println("=== error on commit pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                    continue;
                } catch (Exception e1) {
                    failed(pid);
                    synchronized (this) {
                        System.out.println("=== error on commit pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }

                    try {
                        producer.abortTransaction();
                        log(pid, "brt.produce");
                        failed = false;
                    } catch (Exception e2) {
                        failed = true;
                        log(pid, "err.produce");
                        synchronized (this) {
                            System.out.println("=== error on abort pid:" + pid);
                            System.out.println(e2);
                            e2.printStackTrace();
                        }
                        try {
                            producer.close();
                        } catch (Exception e3) {}
                        producer = null;
                    }
                    continue;
                }
            } else if (task.type == TaskType.CONSUME) {
                try {
                    log(pid, "consume");
                    producer.beginTransaction();

                    HashMap<String, HashMap<Integer, Long>> offsets = new HashMap<>();
                    long version = 0;

                    for (int i=0;i<2;i++) {
                        if (i==1) {
                            version = tracker.version;
                        }
                        ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(10000));
                        if (args.settings.consume_poll_pause_s > 0) {
                            Thread.sleep(args.settings.consume_poll_pause_s * 1000);
                        }
                        var it = records.iterator();
                        while (it.hasNext()) {
                            var record = it.next();
                            log(pid, "poll\t" + record.topic() + "\t" + record.partition() + "\t" + record.offset() + "\t" + record.value());
                            if (!offsets.containsKey(record.topic())) {
                                offsets.put(record.topic(), new HashMap<>());
                            }
                            
                            if (!offsets.get(record.topic()).containsKey(record.partition())) {
                                offsets.get(record.topic()).put(record.partition(), record.offset());
                            } else if (offsets.get(record.topic()).get(record.partition()) < record.offset()) {
                                offsets.get(record.topic()).put(record.partition(), record.offset());
                            } else {
                                if (i==0) {
                                    violation(pid, "non monotonic poll (1)");
                                } else {
                                    if (version == tracker.version) {
                                        violation(pid, "non monotonic poll (2)");
                                    }
                                }
                            }
                        }
                    }

                    var position = new HashMap<TopicPartition, OffsetAndMetadata>();
                    for (var topic : offsets.keySet()) {
                        for (var partition : offsets.get(topic).keySet()) {
                            position.put(new TopicPartition(topic, partition), new OffsetAndMetadata(offsets.get(topic).get(partition) + 1));
                        }
                    }
                    if (args.settings.consume_send_pause_s > 0) {
                        Thread.sleep(args.settings.consume_send_pause_s * 1000);
                    }
                    producer.sendOffsetsToTransaction(position, args.settings.group_id);
                } catch (ProducerFencedException | OutOfOrderSequenceException | AuthorizationException e1) {
                    failed = true;
                    failed(pid);
                    // TODO: mark it is as rejected
                    log(pid, "err.consume");
                    synchronized (this) {
                        System.out.println("=== err.consume: error on send pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                    continue;
                } catch(Exception e1) {
                    failed(pid);
                    synchronized (this) {
                        System.out.println("=== error on sendOffsets pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }

                    try {
                        producer.abortTransaction();
                        failed = false;
                        log(pid, "brt.consume");
                    } catch (Exception e2) {
                        failed = true;
                        log(pid, "err.consume");
                        synchronized (this) {
                            System.out.println("=== err.consume: error on abort pid:" + pid);
                            System.out.println(e2);
                            e2.printStackTrace();
                        }
                        try {
                            producer.close();
                        } catch (Exception e3) {}
                        producer = null;
                    }
                    continue;
                }

                try {
                    if (args.settings.consume_commit_pause_s > 0) {
                        Thread.sleep(args.settings.consume_commit_pause_s * 1000);
                    }
                    producer.commitTransaction();
                    failed = false;
                    log(pid, "cmt.consume");
                    succeeded(pid);
                } catch (ProducerFencedException | OutOfOrderSequenceException | AuthorizationException e1) {
                    failed = true;
                    failed(pid);
                    // TODO: mark it is as rejected
                    log(pid, "err.consume");
                    synchronized (this) {
                        System.out.println("=== err.consume: error on commit pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                    continue;
                } catch (TimeoutException | InterruptException e1) {
                    failed = true;
                    failed(pid);
                    log(pid, "err.consume");
                    synchronized (this) {
                        System.out.println("=== err.consume: error on commit pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                    continue;
                } catch (Exception e1) {
                    failed(pid);
                    synchronized (this) {
                        System.out.println("=== error on commit pid:" + pid);
                        System.out.println(e1);
                        e1.printStackTrace();
                    }

                    try {
                        producer.abortTransaction();
                        failed = false;
                        log(pid, "brt.consume");
                    } catch (Exception e2) {
                        failed = true;
                        log(pid, "err.consume");
                        synchronized (this) {
                            System.out.println("=== err.consume: error on abort pid:" + pid);
                            System.out.println(e2);
                            e2.printStackTrace();
                        }
                        try {
                            producer.close();
                        } catch (Exception e3) {}
                        producer = null;
                    }
                    continue;
                }
            }
        }
    }

    private Producer<String, String> createProducer(int pid) {
        Producer<String, String> producer = null;
        
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
        props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 3000);
        // default value: 100
        props.put(ProducerConfig.RETRY_BACKOFF_MS_CONFIG, 100);
        // default value: 300000
        props.put(ProducerConfig.METADATA_MAX_AGE_CONFIG, 10000);
        // default value: 300000
        props.put(ProducerConfig.METADATA_MAX_IDLE_CONFIG, 10000);
        props.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, 1000);
        props.put(ProducerConfig.SOCKET_CONNECTION_SETUP_TIMEOUT_MS_CONFIG, 500);
        props.put(ProducerConfig.SOCKET_CONNECTION_SETUP_TIMEOUT_MAX_MS_CONFIG, 1000);
        
        props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        props.put(ProducerConfig.RETRIES_CONFIG, 5);
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "tx-" + pid);

        producer =  new KafkaProducer<>(props);
        producer.initTransactions();
        return producer;
    }
}