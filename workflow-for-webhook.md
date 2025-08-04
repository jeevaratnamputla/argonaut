When a POST request hits /webhook, Flask does the following:

Calls process_slack_event().

Inside this function:

Logs Webhook endpoint hit.

Runs verify_slack_request(request). If that fails, it calls abort(403) to block the request.

Extracts data = request.get_json().

Logs the data received.

If it's a Slack url_verification challenge, it responds with the challenge and exits.

Otherwise, it starts a background thread:

Thread(target=process_in_background, args=(data,)).start()
Responds immediately with {"ok": True}.

Meanwhile, process_in_background(data) runs in a separate thread and handles the actual Slack event logic, like:

Parsing the message.

Extracting commands or user input.

Running logic based on "RUN" or "HELP".

Posting responses back to Slack.