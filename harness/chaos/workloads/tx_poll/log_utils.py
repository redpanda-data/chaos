from enum import Enum

class State(Enum):
    STARTED = 0
    CONSTRUCTING_PRODUCER = 1
    CONSTRUCTED_PRODUCER = 2
    ERR_PRODUCER = 3
    CONSTRUCTING_CONSUMER = 4
    CONSTRUCTED_CONSUMER = 5
    ERR_CONSUMER = 6
    PRODUCE = 7
    SEND = 8
    OFFSETS = 9
    ERR_PRODUCE = 10
    ABORT_PRODUCE = 11
    COMMIT_PRODUCE = 12
    CONSUME = 13
    POLL = 14
    ERR_CONSUME = 15
    ABORT_CONSUME = 16
    COMMIT_CONSUME = 17
    VIOLATION = 18
    EVENT = 19
    LOG = 20
    SUBSCRIBE = 21
    OK_SUBSCRIBE = 22
    ERR_SUBSCRIBE = 23

cmds = {
    "started": State.STARTED,
    "constructing.producer": State.CONSTRUCTING_PRODUCER,
    "constructed.producer": State.CONSTRUCTED_PRODUCER,
    "err.producer": State.ERR_PRODUCER,
    "constructing.consumer": State.CONSTRUCTING_CONSUMER,
    "constructed.consumer": State.CONSTRUCTED_CONSUMER,
    "err.consumer": State.ERR_CONSUMER,
    "produce": State.PRODUCE,
    "send": State.SEND,
    "offsets": State.OFFSETS,
    "err.produce": State.ERR_PRODUCE,
    "brt.produce": State.ABORT_PRODUCE,
    "cmt.produce": State.COMMIT_PRODUCE,
    "consume": State.CONSUME,
    "poll": State.POLL,
    "err.consume": State.ERR_CONSUME,
    "brt.consume": State.ABORT_CONSUME,
    "cmt.consume": State.COMMIT_CONSUME,
    "subscribe": State.SUBSCRIBE,
    "ok.subscribe": State.OK_SUBSCRIBE,
    "err.subscribe": State.ERR_SUBSCRIBE,
    "event": State.EVENT,
    "violation": State.VIOLATION,
    "log": State.LOG
}

transitions = {
    State.STARTED: [State.CONSTRUCTING_PRODUCER],
    State.CONSTRUCTING_PRODUCER: [State.CONSTRUCTED_PRODUCER, State.ERR_PRODUCER],
    State.ERR_PRODUCER: [State.CONSTRUCTING_PRODUCER],
    State.CONSTRUCTED_PRODUCER: [State.CONSTRUCTING_CONSUMER, State.PRODUCE, State.CONSUME, State.SUBSCRIBE],
    State.CONSTRUCTING_CONSUMER: [State.CONSTRUCTED_CONSUMER, State.ERR_CONSUMER],
    State.ERR_CONSUMER: [State.CONSTRUCTING_CONSUMER],
    State.CONSTRUCTED_CONSUMER: [State.PRODUCE, State.CONSUME, State.SUBSCRIBE],
    State.SUBSCRIBE: [State.OK_SUBSCRIBE, State.ERR_SUBSCRIBE],
    State.OK_SUBSCRIBE: [State.PRODUCE, State.CONSUME, State.SUBSCRIBE],
    State.ERR_SUBSCRIBE: [State.PRODUCE, State.CONSUME, State.SUBSCRIBE],
    State.PRODUCE: [State.SEND],
    State.SEND: [State.OFFSETS, State.ABORT_PRODUCE, State.ERR_PRODUCE],
    State.OFFSETS: [State.SEND, State.COMMIT_PRODUCE, State.ABORT_PRODUCE, State.ERR_PRODUCE],
    State.ABORT_PRODUCE: [State.PRODUCE, State.CONSUME, State.SUBSCRIBE],
    State.COMMIT_PRODUCE: [State.PRODUCE, State.CONSUME, State.SUBSCRIBE],
    State.ERR_PRODUCE: [State.CONSTRUCTING_PRODUCER],
    State.CONSUME: [State.POLL, State.ABORT_CONSUME, State.ERR_CONSUME, State.COMMIT_CONSUME],
    State.POLL: [State.POLL, State.ABORT_CONSUME, State.ERR_CONSUME, State.COMMIT_CONSUME],
    State.ABORT_CONSUME: [State.PRODUCE, State.CONSUME, State.SUBSCRIBE],
    State.ERR_CONSUME: [State.CONSTRUCTING_PRODUCER],
    State.COMMIT_CONSUME: [State.PRODUCE, State.CONSUME, State.SUBSCRIBE]
}

phantoms = [ State.EVENT, State.VIOLATION, State.LOG ]