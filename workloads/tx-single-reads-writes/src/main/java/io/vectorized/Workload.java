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
import java.util.HashSet;
import java.util.LinkedList;
import java.util.Queue;
import java.util.Collections;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import java.time.Duration;

public class Workload {
    static enum TxStatus {
        ONGOING, COMMITTING, ABORTING, COMMITTED
    }
    
    static class TxRecord {
        public int wid;
        public long tid;
        public TxStatus status;
        public HashSet<Integer> seen;
        public boolean expired;
        public boolean ended;
        public Queue<Long> ops;
        public long started_us;
        public long seen_us;
    }

    static class OpRecord {
        public long oid;
        public long offset;
        public long tid;
    }

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

    private long last_op_id = 0;
    private synchronized long get_op_id() {
        return ++this.last_op_id;
    }

    private long last_tx_id = 0;
    private synchronized long get_tx_id() {
        return ++this.last_tx_id;
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

    private volatile ArrayList<Thread> threads;

    private HashMap<Long, TxRecord> txes;
    private HashMap<Integer, HashMap<Long, Long>> next_tid;
    private HashMap<Long, OpRecord> ops;

    private HashMap<Long, Long> seen_offset_oid;
    private HashMap<Long, Long> seen_next_offset;
    private Queue<Long> seen_offsets;

    private HashMap<Integer, Long> read_offset_front;

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
        ops_info = new HashMap<>();
        txes = new HashMap<>();
        next_tid = new HashMap<>();
        ops = new HashMap<>();
        seen_offset_oid = new HashMap<>();
        seen_next_offset = new HashMap<>();
        seen_offsets = new LinkedList<>();
        read_offset_front = new HashMap<>();

        int thread_id=0;
        threads = new ArrayList<>();
        for (int i=0;i<this.args.settings.writes;i++) {
            final var j=thread_id++;
            next_tid.put(j, new HashMap<>());
            should_reset.put(j, false);
            ops_info.put(j, new App.OpsInfo());
            threads.add(new Thread(() -> { 
                try {
                    writeProcess(j);
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

        for (int i=0;i<this.args.settings.reads;i++) {
            final var j=thread_id++;
            should_reset.put(j, false);
            read_offset_front.put(j, -1L);
            threads.add(new Thread(() -> { 
                try {
                    readProcess(j);
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

    private void writeProcess(int wid) throws Exception {
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
        props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "tx-" + wid);
    
    
        Producer<String, String> producer = null;
    
        log(wid, "started\t" + args.server);
        long j = 0;
        long prev_tid = -1L;
    
        while (is_active) {
            j++;
            tick();
    
            synchronized(this) {
                if (should_reset.get(wid)) {
                    should_reset.put(wid, false);
                    if (producer != null) {
                        try {
                            producer.close();
                            producer = null;
                        } catch(Exception e) {}
                    }
                }
            }
    
            try {
                if (producer == null) {
                    log(wid, "constructing");
                    producer = new KafkaProducer<>(props);
                    producer.initTransactions();
                    log(wid, "constructed");
                    continue;
                }
            } catch (Exception e1) {
                log(wid, "err");
                System.out.println(e1);
                e1.printStackTrace();
                failed(wid);
                try {
                    if (producer != null) {
                        producer.close();
                    }
                } catch(Exception e2) { }
                producer = null;
                continue;
            }
    
    
            var tx = new TxRecord();
            tx.wid = wid;
            tx.tid = get_tx_id();
            tx.status = TxStatus.ONGOING;
            tx.seen = new HashSet<>();
            tx.expired = false;
            tx.ended = true;
            tx.started_us = System.nanoTime() / 1000;
            tx.seen_us = -1;
            tx.ops = new LinkedList<>();
            
            synchronized(this) {
                next_tid.get(wid).put(prev_tid, tx.tid);
                txes.put(tx.tid, tx);
                prev_tid = tx.tid;
            }
    
            log(wid, "tx\t" + tx.tid);
            producer.beginTransaction();
    
            long tx_min_offset = Long.MAX_VALUE;
            long tx_max_offset = Long.MIN_VALUE;
            try {
                for (int i=0;i<10;i++) {
                    var op = new OpRecord();
                    op.oid = get_op_id();
                    op.tid = tx.tid;
                    op.offset = -1;
                    synchronized(this) {
                        tx.ops.add(op.oid);
                        ops.put(op.oid, op);
                    }
                    var offset = producer.send(new ProducerRecord<String, String>(args.topic, args.server, "" + op.oid)).get().offset();
                    tx_min_offset = Math.min(tx_min_offset, offset);
                    tx_max_offset = Math.max(tx_max_offset, offset);
                    synchronized(this) {
                        if (op.offset < 0) {
                            op.offset = offset;
                        }
                        if (op.offset != offset) {
                            violation(wid, "a write with oid:" + op.oid + " & offset:" + offset + " was observed before with offset:" + op.offset);
                        }
                    }
                }
            } catch (Exception e1) {
                System.out.println("error on produce => aborting tx");
                System.out.println(e1);
                e1.printStackTrace();
    
                synchronized(this) {
                    if (tx.status != TxStatus.ONGOING) {
                        violation(wid, "tx failed before commit but its status isn't ongoing: " + tx.status.name());
                    }
                    tx.status = TxStatus.ABORTING;
                    tx.ended = true;
                }
    
                try {
                    log(wid, "brt");
                    producer.abortTransaction();
                    if (tx_min_offset <= tx_max_offset) {
                        log(wid, "ok\t" + tx_min_offset + "\t" + tx_max_offset);
                    } else {
                        log(wid, "ok");
                    }
                    failed(wid);
                } catch (Exception e2) {
                    System.out.println("error on abort => reset producer");
                    System.out.println(e2);
                    e2.printStackTrace();
                    if (tx_min_offset <= tx_max_offset) {
                        log(wid, "err\t" + tx_min_offset + "\t" + tx_max_offset);
                    } else {
                        log(wid, "err");
                    }
                    failed(wid);
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                }
    
                continue;
            }
    
            try {
                log(wid, "cmt");
                synchronized(this) {
                    if (tx.status != TxStatus.ONGOING) {
                        violation(wid, "an ongoing tx changed its status before committing: " + tx.status.name());
                    }
                    tx.status = TxStatus.COMMITTING;
                }
                producer.commitTransaction();
                synchronized(this) {
                    if (tx.status == TxStatus.COMMITTING) {
                        tx.status = TxStatus.COMMITTED;
                    }
                    if (tx.status != TxStatus.COMMITTED) {
                        violation(wid, "a committed tx can't have status: " + tx.status.name());
                    }
                    tx.ended = true;
                    if (tx.expired) {
                        txes.remove(tx.tid);
                        for (var oid : tx.ops) {
                            ops.remove(oid);
                        }
                    }
                }
                log(wid, "ok\t" + tx_min_offset + "\t" + tx_max_offset);
                succeeded(wid);
            } catch (Exception e1) {
                synchronized(this) {
                    tx.ended = true;
                }
                System.out.println("error on commit => reset producer");
                System.out.println(e1);
                e1.printStackTrace();
                log(wid, "err\t" + tx_min_offset + "\t" + tx_max_offset);
                failed(wid);
                try {
                    producer.close();
                } catch (Exception e3) {}
                producer = null;
            }
        }
    
        if (producer != null) {
            try {
                producer.close();
            } catch (Exception e) { }
        }
    }

    private void readProcess(int rid) throws Exception {
        var tp = new TopicPartition(args.topic, 0);
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
        HashMap<Integer, Long> prev_tid_by_wid = new HashMap<>();
        synchronized (this) {
            for (var wid : next_tid.keySet()) {
                prev_tid_by_wid.put(wid, -1L);
            }
        }

        log(rid, "started\t" + args.server + "\tconsumer");

        long prev_offset = -1;
        HashMap<Long, Queue<Long>> local_tx_ops = new HashMap<>();

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

                synchronized(this) {
                    // monotonicity
                    if (offset <= prev_offset) {
                        violation(rid, "reads must be monotonic but observed " + offset + " after " + prev_offset);
                    }

                    // all readers see the same sequence
                    if (seen_offset_oid.containsKey(offset)) {
                        if (seen_offset_oid.get(offset) != oid) {
                            violation(rid, "read " + oid + "@" + offset + " but " + seen_offset_oid.get(offset) + "@" + offset + " was already seen");
                        }
                        if (!seen_next_offset.containsKey(prev_offset)) {
                            violation(rid, "offset " + offset + " is aleady seen but it doesn't go after " + prev_offset);
                        }
                        if (seen_next_offset.get(prev_offset) != offset) {
                            violation(rid, "read " + prev_offset + "->" + offset + " after " + prev_offset + "->" + seen_next_offset.get(prev_offset) + " was already seen");
                        }
                    } else {
                        seen_offset_oid.put(offset, oid);
                        seen_next_offset.put(prev_offset, offset);
                        seen_offsets.add(offset);
                    }
                    prev_offset = offset;
                    
                    // gc aux structure needed for previous step
                    read_offset_front.put(rid, offset);
                    long min_offset = offset;
                    for (var seen_offset : read_offset_front.values()) {
                        min_offset = Math.min(min_offset, seen_offset);
                    }
                    if (min_offset == offset) {
                        while (seen_offsets.element() < offset) {
                            var old = seen_offsets.remove();
                            seen_offset_oid.remove(old);
                            seen_next_offset.remove(old);
                        }
                    }

                    // validating integraty of oid/offset
                    if (!ops.containsKey(oid)) {
                        violation(rid, "observed unknown oid:" + oid);
                    }
                    var op = ops.get(oid);
                    if (op.offset < 0) {
                        op.offset = offset;
                    }
                    if (op.offset != offset) {
                        violation(rid, "read " + oid + "@" + offset + " but " + oid + "@" + op.offset + " was already seen");
                    }

                    if (!txes.containsKey(op.tid)) {
                        violation(rid, "unknown tid: " + op.tid + " assosiated with " + oid + "@" + offset);
                    }
                    var tx = txes.get(op.tid);
                    if (tx.status == TxStatus.ONGOING) {
                        violation(rid, "observed tx before a commit attempt was made; tid:" + op.tid);
                    }
                    if (tx.status == TxStatus.ABORTING) {
                        violation(rid, "observed aborted tx; tid:" + op.tid);
                    }
                    if (tx.status == TxStatus.COMMITTING) {
                        tx.status = TxStatus.COMMITTED;
                    }
                    if (tx.seen_us < 0) {
                        tx.seen_us = System.nanoTime() / 1000;
                        log(rid, "seen\t" + (tx.seen_us - tx.started_us));
                    }

                    if (!local_tx_ops.containsKey(tx.tid)) {
                        var prev_tid = prev_tid_by_wid.get(tx.wid);
                        var curr_tid = prev_tid;
                        // checking for missing transacitons before tx
                        while (curr_tid != tx.tid) {
                            if (curr_tid < 0) {
                                curr_tid = next_tid.get(tx.wid).get(curr_tid);
                                continue;
                            }
                            if (!txes.containsKey(curr_tid)) {
                                throw new Exception("can't find tx for tid:" + curr_tid);
                            }
                            var curr_tx = txes.get(curr_tid);
                            if (curr_tx.status == TxStatus.ONGOING) {
                                curr_tx.status = TxStatus.ABORTING;
                                curr_tx.seen.add(rid);
                            } else if (curr_tx.status == TxStatus.ABORTING) {
                                curr_tx.seen.add(rid);
                            } else if (curr_tx.status == TxStatus.COMMITTING) {
                                curr_tx.status = TxStatus.ABORTING;
                                curr_tx.seen.add(rid);
                            } else if (curr_tx.status == TxStatus.COMMITTED) {
                                if (curr_tid != prev_tid) {
                                    violation(rid, "observed tid:" + op.tid + " but skipped over tid:" + curr_tid);
                                }
                                curr_tx.seen.add(rid);
                            } else {
                                throw new Exception("Unknown status: " + curr_tx.status.name());
                            }
                            var next = next_tid.get(tx.wid).get(curr_tid);
                            if (read_offset_front.keySet().stream().allMatch(x -> curr_tx.seen.contains(x))) {
                                next_tid.get(tx.wid).remove(curr_tid);
                                curr_tx.expired = true;
                                if (curr_tx.ended) {
                                    txes.remove(curr_tx.tid);
                                    for (var id : curr_tx.ops) {
                                        ops.remove(id);
                                    }
                                }
                            }
                            curr_tid = next;
                        }
                        prev_tid_by_wid.put(tx.wid, tx.tid);
                        local_tx_ops.put(tx.tid, new LinkedList<>(tx.ops));
                    }

                    if (local_tx_ops.get(tx.tid).element() != oid) {
                        violation(rid, "expected next read record of tid:" + tx.tid + " has oid:" + local_tx_ops.get(tx.tid).element() + " but observed oid:" + oid);
                    }
                    local_tx_ops.get(tx.tid).remove();
                    if (local_tx_ops.get(tx.tid).size()==0) {
                        local_tx_ops.remove(tx.tid);
                    }
                }
            }
        }
    }
}