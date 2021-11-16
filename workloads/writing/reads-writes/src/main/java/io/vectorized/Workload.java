package io.vectorized;
import java.io.*;
import java.util.Properties;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.TopicPartition;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Semaphore;
import java.util.Collections;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

import javax.swing.plaf.synth.SynthButtonUI;

import java.lang.Thread;
import org.apache.kafka.common.errors.TimeoutException;
import org.apache.kafka.common.errors.NotLeaderOrFollowerException;
import java.io.BufferedWriter;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Queue;
import java.util.LinkedList;
import java.time.Duration;

public class Workload {
    static class WriteInfo {
        public int thread_id;
        public long op;
        public long curr_offset;
        public long last_offset;
        public boolean has_write_passed;
        public boolean is_expired;
    }
    
    public volatile long succeeded_writes = 0;
    public volatile long failed_writes = 0;
    public volatile long timedout_writes = 0;
    public volatile boolean is_active = false;
    
    private volatile App.InitBody args;
    private volatile ArrayList<Thread> write_threads;
    private volatile ArrayList<Thread> read_threads;
    private BufferedWriter opslog;
    private long past_us;
    private long before_us = -1;
    private long last_op = 0;

    long last_known_offset;
    Queue<Long> read_offsets;
    HashMap<Integer, Long> read_fronts;
    HashMap<Long, Long> next_offset;
    HashMap<Long, WriteInfo> write_by_op;
    HashMap<Long, WriteInfo> write_by_offset;
    HashMap<Integer, Queue<Long>> known_writes;
    HashMap<Integer, Semaphore> semaphores;

    synchronized long get_op() {
        return ++this.last_op;
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

        last_known_offset = -1;
        write_by_op = new HashMap<>();
        write_by_offset = new HashMap<>();
        read_fronts = new HashMap<>();
        next_offset = new HashMap<>();
        read_offsets = new LinkedList<>();
        semaphores = new HashMap<>();
        known_writes = new HashMap<>();
        
        int thread_id=0;
        write_threads = new ArrayList<>();
        for (int i=0;i<this.args.settings.writes;i++) {
            final var j=thread_id++;
            write_threads.add(new Thread(() -> { 
                try {
                    writeProcess(j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                }
            }));
        }

        read_threads = new ArrayList<>();
        for (int i=0;i<this.args.settings.reads;i++) {
            final var j=thread_id++;
            read_fronts.put(i, -1L);
            read_threads.add(new Thread(() -> { 
                try {
                    readProcess(j);
                } catch(Exception e) {
                    System.out.println(e);
                    e.printStackTrace();
                }
            }));
        }
        
        for (var th : write_threads) {
            th.start();
        }

        for (var th : read_threads) {
            th.start();
        }
    }

    public void stop() throws Exception {
        is_active = false;
        for (var th : write_threads) {
            th.join();
        }
        for (var th : read_threads) {
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

    private synchronized void violation(int thread_id, String message) throws Exception {
        var now_us = System.nanoTime() / 1000;
        if (now_us < past_us) {
            throw new Exception("Time cant go back, observed: " + now_us + " after: " + before_us);
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

    private void readProcess(int thread_id) throws Exception {
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

        log(thread_id, "started\t" + args.server + "\tconsumer");

        long prev_offset = -1;
        while (is_active) {
            try {
                if (consumer == null) {
                    log(thread_id, "constructing");
                    consumer = new KafkaConsumer<>(props);
                    consumer.assign(tps);
                    consumer.seekToBeginning(tps);
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

            ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(10000));
            var it = records.iterator();
            while (it.hasNext()) {
                var record = it.next();

                if (!record.key().equals(args.server)) {
                    continue;
                }

                synchronized(this) {
                    long offset = record.offset();
                    last_known_offset = Math.max(last_known_offset, offset);
                    if (offset <= prev_offset) {
                        violation(thread_id, "reads must be monotonic but observed " + offset + " after " + prev_offset);
                    }

                    long op = Long.parseLong(record.value());
                    if (!write_by_op.containsKey(op)) {
                        violation(thread_id, "read " + op + "@" + offset + ": duplication or truncation");
                    }
                    var write = write_by_op.get(op);

                    if (next_offset.containsKey(prev_offset)) {
                        if (next_offset.get(prev_offset) != offset) {
                            violation(thread_id, "read " + offset + " after " + prev_offset + " while abother thread read " + next_offset.get(prev_offset));
                        }
                    } else {
                        semaphores.get(write.thread_id).release();
                        next_offset.put(prev_offset, offset);
                        read_offsets.add(offset);
                    }
                    prev_offset = offset;

                    if (write.curr_offset == -1) {
                        write.curr_offset = offset;
                        write_by_offset.put(offset, write);
                    }
                    if (write.curr_offset != offset) {
                        violation(thread_id, "read " + op + "@" + offset + " conflicting with already observed " + op + "@" + write.curr_offset);
                    }
                    if (write.curr_offset <= write.last_offset) {
                        violation(thread_id, "read " + op + "@" + offset + " while " + write.last_offset + " was already known when the write started");
                    }

                    read_fronts.put(thread_id, offset);
                    var min_front = offset;
                    for (var rid : read_fronts.keySet()) {
                        min_front = Math.min(min_front, read_fronts.get(rid));
                    }

                    if (min_front == offset) {
                        var thread_known = known_writes.get(write.thread_id);
                        if (thread_known.size()>0) {
                            if (thread_known.peek() == offset) {
                                thread_known.remove();
                            } else if (thread_known.peek() < offset) {
                                violation(thread_id, "read " + offset + " but skipped " + thread_known.peek());
                            }
                        }
                    }

                    while (read_offsets.size() > 0 && read_offsets.peek() < min_front) {
                        var expired_offset = read_offsets.remove();
                        if (!write_by_offset.containsKey(expired_offset)) {
                            violation(thread_id, "int. assert violation");
                        }
                        var expired_write = write_by_offset.get(expired_offset);
                        if (expired_write.has_write_passed) {
                            write_by_offset.remove(expired_offset);
                            write_by_op.remove(expired_write.op);
                        } else {
                            expired_write.is_expired = true;
                        }
                        next_offset.remove(expired_offset);
                    }
                }
            }
        }   
    }

    private void writeProcess(int thread_id) throws Exception {
        Semaphore semaphore = new Semaphore(1, false);
        synchronized(this) {
            semaphores.put(thread_id, semaphore);
            known_writes.put(thread_id, new LinkedList<>());
        }
        
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
                synchronized(this) {
                    var info = new WriteInfo();

                    info.thread_id = thread_id;
                    info.op = op;
                    info.curr_offset = -1;
                    info.last_offset = last_known_offset;
                    info.has_write_passed = false;
                    info.is_expired = false;
                    
                    write_by_op.put(op, info);
                }
                var f = producer.send(new ProducerRecord<String, String>(args.topic, args.server, "" + op));
                var m = f.get();
                succeeded_writes++;
                var offset = m.offset();
                var should_acquire = true;
                synchronized(this) {
                    var write = write_by_op.get(op);

                    if (write.curr_offset == -1) {
                        write.curr_offset = offset;
                        write_by_offset.put(offset, write);
                    }
                    if (write.curr_offset != offset) {
                        violation(thread_id, "read " + op + "@" + offset + " conflicting with already observed " + op + "@" + write.curr_offset);
                    }
                    if (write.curr_offset <= write.last_offset) {
                        violation(thread_id, "read " + op + "@" + offset + " while " + write.last_offset + " was already known when the write started");
                    }
                    
                    write.has_write_passed = true;

                    if (write.is_expired) {
                        write_by_offset.remove(offset);
                        write_by_op.remove(op);
                        should_acquire = false;
                    } else {
                        known_writes.get(thread_id).add(offset);
                    }

                    last_known_offset = Math.max(last_known_offset, write.curr_offset);
                }
                if (should_acquire) {
                    semaphore.acquire();
                }
                log(thread_id, "ok\t" + offset);
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
}
