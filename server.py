from flask import Flask, render_template, request
from flask_sockets import Sockets

from SpeechClientBridge import SpeechClientBridge
from google.cloud.speech import enums
from google.cloud.speech import types
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client
import time
import pdb
import os

current_time_ms = lambda: int(round(time.time() * 1000))

import json
import base64

HTTP_SERVER_PORT = int(os.environ.get("PORT", 8080))

config = types.RecognitionConfig(
    encoding=enums.RecognitionConfig.AudioEncoding.MULAW,
    sample_rate_hertz=8000,
    language_code='en-US',
    model='phone_call',
    use_enhanced=True)
streaming_config = types.StreamingRecognitionConfig(
    config=config,
    interim_results=True,
    single_utterance=False)

app = Flask(__name__)
sockets = Sockets(app)

streamSid = None
callSid = None
thresholdMS = 3000
startTime = current_time_ms()
transcribeText = []

account_sid = ''
auth_token = ''
client = Client(account_sid, auth_token)

@app.route('/answer', methods=['POST'])
def return_twiml():
    print("POST TwiML")
    # pdb.set_trace()
    return render_template('streams.xml', host=(request.environ['HTTP_HOST']), timeout_sec=30)

# [START dialogflow_detect_intent_text]
def detect_intent_texts(texts=[], language_code="en-US"):
    """Returns the result of detect intent with texts as inputs.
    Using the same `session_id` between requests allows continuation
    of the conversation."""
    import dialogflow_v2 as dialogflow
    session_client = dialogflow.SessionsClient()

    project_id = "voicebot-audiostream-poc"
    session_id = streamSid
    session = session_client.session_path(project_id, session_id)
    print('Session path: {}\n'.format(session))

    for text in texts:
        text_input = dialogflow.types.TextInput(
            text=text, language_code=language_code)

        query_input = dialogflow.types.QueryInput(text=text_input)

        response = session_client.detect_intent(
            session=session, query_input=query_input)

        print('=' * 20)
        print('Query text: {}'.format(response.query_result.query_text))
        print('Detected intent: {} (confidence: {})\n'.format(
            response.query_result.intent.display_name,
            response.query_result.intent_detection_confidence))
        print('Fulfillment text: {}\n'.format(
            response.query_result.fulfillment_text))

        if not (response.query_result.fulfillment_text is None):
            resp = VoiceResponse()
            resp.say(response.query_result.fulfillment_text, voice='alice')
            call = client.calls(callSid).update(twiml=str(resp))
# [END dialogflow_detect_intent_text]

def on_transcription_response(response):
    if not response.results:
        return

    result = response.results[0]
    if not result.alternatives:
        return

    transcription = result.alternatives[0].transcript

    global transcribeText
    global thresholdMS
    global startTime
    current_time = current_time_ms()

    print("Transcription: " + transcription)
    print(callSid)
    print(streamSid)
    print( current_time - startTime)
    print(result)

    transcribeText.append(transcription)

    if (current_time - startTime) > thresholdMS:
        detect_intent_texts(transcribeText)
        startTime = current_time
        transcribeText.clear()

# @sockets.route('/web')
# def webS(webSoc):
#     print("web: WS connection opened")
#
#     while not webSoc.closed:
#         message = webSoc.receive()

@sockets.route('/')
def transcript(ws):
    print("WS connection opened")
    bridge = SpeechClientBridge(
        streaming_config,
        on_transcription_response
    )

    while not ws.closed:
        message = ws.receive()
        if message is None:
            bridge.terminate()
            break

        data = json.loads(message)
        if data["event"] in ("connected", "start"):
            print(f"Media WS: Received event '{data['event']}': {message}")
            if data["event"] in ("start"):
                global streamSid
                global callSid
                streamSid = data["start"]["streamSid"]
                callSid = data["start"]["callSid"]
                print(callSid)
                print(streamSid)
            continue
        if data["event"] == "media":
            media = data["media"]
            chunk = base64.b64decode(media["payload"])
            bridge.add_request(chunk)
        if data["event"] == "stop":
            print(f"Media WS: Received event 'stop': {message}")
            print("Stopping...")
            break

    bridge.terminate()
    print("WS connection closed")

print("__name__")
print(__name__)

if __name__ == '__main__':
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler

    server = pywsgi.WSGIServer(('', HTTP_SERVER_PORT), app, handler_class=WebSocketHandler)
    print("Server listening on: http://localhost:" + str(HTTP_SERVER_PORT))
    server.serve_forever()
