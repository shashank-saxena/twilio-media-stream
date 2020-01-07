web: gunicorn server:app -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 --timeout 55 --keep-alive 5 --log-level debug
