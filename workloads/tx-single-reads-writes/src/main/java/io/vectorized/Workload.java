package io.vectorized;
import java.io.*;
import java.util.Properties;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import java.util.concurrent.ExecutionException;
import java.lang.Thread;
import org.apache.kafka.common.errors.TimeoutException;
import org.apache.kafka.common.errors.NotLeaderOrFollowerException;
import org.apache.kafka.common.errors.OutOfOrderSequenceException;
import org.apache.kafka.common.errors.UnknownProducerIdException;
import java.util.concurrent.Future;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.KafkaException;
import java.io.BufferedWriter;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.HashMap;

public class Workload {
    static class WriteInfo {
        public int thread_id;
        public long op_id;
        public long tx_id;
        public long curr_offset;
        public long last_offset;
    }

    static class TxInfo {
        public int thread_id;
        public long tx_id;
        public boolean has_decided;
        public boolean is_committed;
    }

    public volatile boolean is_active = false;
    
    private volatile App.InitBody args;
    private volatile ArrayList<Thread> threads;
    private BufferedWriter opslog;
    private long past_us;
    private long before_us = -1;
    private long last_op_id = 0;
    private long last_tx_id = 0;

    private long last_success_us = -1;
    private HashMap<Integer, Boolean> should_reset;
    private HashMap<Integer, App.OpsInfo> ops_info;

    HashMap<Long, WriteInfo> write_by_op;
    HashMap<Long, WriteInfo> write_by_offset;

    private synchronized long get_op_id() {
        return ++this.last_op_id;
    }

    private synchronized long get_tx_id() {
        return ++this.last_tx_id;
    }

    private synchronized void tick() {
        var now_us = Math.max(last_success_us, System.nanoTime() / 1000);
        if (now_us - last_success_us > 10000*1000) {
            for (var thread_id : should_reset.keySet()) {
                should_reset.put(thread_id, true);
            }
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
        
        should_reset = new HashMap<>();
        ops_info = new HashMap<>();
        write_by_op = new HashMap<>();
        write_by_offset = new HashMap<>();

        threads = new ArrayList<>();
        for (int i=0;i<this.args.settings.writes;i++) {
            final var j=i;
            should_reset.put(j, false);
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

        if (this.args.settings.reads != 0) {
            throw new Exception("reads are not supported yet");
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
        props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "tx-" + thread_id);


        Producer<String, String> producer = null;

        log(thread_id, "started\t" + args.server);
        long j = 0;

        while (is_active) {
            j++;
            tick();

            synchronized(this) {
                if (should_reset.get(thread_id)) {
                    should_reset.put(thread_id, false);
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
                    log(thread_id, "constructing");
                    producer = new KafkaProducer<>(props);
                    producer.initTransactions();
                    log(thread_id, "constructed");
                    continue;
                }
            } catch (Exception e) {
                log(thread_id, "err");
                System.out.println(e);
                e.printStackTrace();
                failed(thread_id);
                continue;
            }


            long tx_id = get_tx_id();
            log(thread_id, "tx\t" + tx_id);
            
            producer.beginTransaction();

            try {
                for (int i=0;i<10;i++) {
                    long op_id = get_op_id();
                    log(thread_id, "op\t" + op_id);
                    var f = producer.send(new ProducerRecord<String, String>(args.topic, args.server, "" + op_id));
                    log(thread_id, "idx\t" + f.get().offset());
                }
            } catch (Exception e1) {
                System.out.println("error on produce => aborting tx");
                System.out.println(e1);
                e1.printStackTrace();

                try {
                    log(thread_id, "brt");
                    producer.abortTransaction();
                    log(thread_id, "ok");
                    failed(thread_id);
                } catch (Exception e2) {
                    System.out.println("error on abort => reset producer");
                    System.out.println(e2);
                    e2.printStackTrace();
                    log(thread_id, "err");
                    failed(thread_id);
                    try {
                        producer.close();
                    } catch (Exception e3) {}
                    producer = null;
                }

                continue;
            }

            try {
                log(thread_id, "cmt");
                producer.commitTransaction();
                log(thread_id, "ok");
                succeeded(thread_id);
            } catch (Exception e1) {
                System.out.println("error on commit => reset producer");
                System.out.println(e1);
                e1.printStackTrace();
                log(thread_id, "err");
                failed(thread_id);
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
}