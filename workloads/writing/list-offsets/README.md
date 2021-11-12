mvn clean dependency:copy-dependencies package

java -cp target/list-offsets-1.0-SNAPSHOT.jar:target/dependency/* io.vectorized.App

curl -X POST http://127.0.0.1:8080/init -H 'Content-Type: application/json' -d '{"topic":"topic1","brokers":"127.0.0.1:9092","experiment":"experiment1", "server":"server1", "settings": { "concurrency": 1 }}'

curl -X POST http://127.0.0.1:8080/start

curl -X GET http://127.0.0.1:8080/info