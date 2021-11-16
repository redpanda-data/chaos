package io.vectorized;

import com.google.gson.Gson;
import java.io.*;

import static spark.Spark.*;
import spark.*;

// java -cp $(pwd)/target/tx-performance-1.0-SNAPSHOT.jar:$(pwd)/target/dependency/* io.vectorized.App
public class App
{
    public static class WorkflowSettings {
        public int writes;
        public int reads;
    }
    
    public static class InitBody {
        public String experiment;
        public String server;
        public String brokers;
        public String topic;
        public WorkflowSettings settings;
    }

    public static class Info {
        public boolean is_active;
        public long succeeded_ops = 0;
        public long failed_ops = 0;
    }

    static enum State {
        FRESH,
        INITIALIZED,
        STARTED,
        STOPPED
    }

    public class JsonTransformer implements ResponseTransformer {
        private Gson gson = new Gson();
    
        @Override
        public String render(Object model) {
            return gson.toJson(model);
        }
    }

    State state = State.FRESH;
    
    InitBody params = null;
    Workload workload = null;

    void run() throws Exception {
        port(8080);

        get("/ping", (req, res) -> {
            res.status(200);
            return "";
        });

        get("/info", "application/json", (req, res) -> {
            var info = new Info();
            info.is_active = false;
            info.failed_ops = 0;
            info.succeeded_ops = 0;
            if (workload != null) {
                info.succeeded_ops = workload.succeeded_writes;
                info.failed_ops = workload.failed_writes;
                info.is_active = workload.is_active;
            }
            return info;
        }, new JsonTransformer());

        post("/init", (req, res) -> {
            if (state != State.FRESH) {
                throw new Exception("Unexpected state: " + state);
            }
            state = State.INITIALIZED;

            Gson gson = new Gson();
            
            params = gson.fromJson(req.body(), InitBody.class);
            File root = new File(params.experiment);

            if (!root.mkdir()) {
                throw new Exception("Can't create folder: " + params.experiment);
            }
            
            res.status(200);
            return "";
        });

        post("/event/:name", (req, res) -> {
            var name = req.params(":name");
            workload.event(name);
            res.status(200);
            return "";
        });
        
        post("/start", (req, res) -> {
            if (state != State.INITIALIZED) {
                throw new Exception("Unexpected state: " + state);
            }
            state = State.STARTED;

            workload = new Workload(params);
            workload.start();
            
            //curl -X POST http://127.0.0.1:8080/start -H 'Content-Type: application/json' -d '{"topic":"topic1","brokers":"127.0.0.1:9092"}'
            res.status(200);
            return "";
        });

        post("/stop", (req, res) -> {
            if (state != State.STARTED) {
                throw new Exception("Unexpected state: " + state);
            }
            state = State.STOPPED;
            workload.stop();
            //curl -X POST http://127.0.0.1:8080/start -H 'Content-Type: application/json' -d '{"topic":"topic1","brokers":"127.0.0.1:9092"}'
            res.status(200);
            return "";
        });
    }

    public static void main( String[] args ) throws Exception
    {
        new App().run();
    }
}
