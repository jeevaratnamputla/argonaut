To create a Slack app in your workspace, follow these steps:

Go to the Slack API Page:

Open https://api.slack.com/apps in your browser.

Create a New App:

Click on the "Create New App" button.
You’ll see two options: From scratch or From an app manifest. For a custom app with event subscriptions, choose From scratch.
Name Your App:

In the "App Name" field, enter a name for your Slack app (e.g., Message Webhook App).
Select the Slack workspace where you want to install the app.
Create App:

go to https://api.slack.com/apps
Click Create App to proceed. You’ll be taken to the app’s settings page. choose to create from scratch.
Add Necessary Features and Permissions:

To allow the app to listen to messages in channels, you need to enable Event Subscriptions and OAuth & Permissions.
Set Up Event Subscriptions:

In the left menu, go to Event Subscriptions.
Turn on Event Subscriptions by toggling the switch.
Under Request URL, add the URL of your server endpoint (https://slack-ingress-host/webhook) where Slack will send events (you can add a placeholder URL if you don’t have one set up yet).
Under Subscribe to Bot Events (or Workspace Events), click Add Bot User Event.
Select the event message.channels to listen for messages posted in public channels.
Click Save Changes.
Add OAuth Scopes:

In the left menu, go to OAuth & Permissions.
Under Scopes, add the necessary OAuth scopes for your app. For listening to messages in channels, add:
channels:read (to read channel information)
chat:write (if you want the bot to send messages)
channels:history (to access message history in public channels)
Save your changes.

Install the App to Your Workspace:

Still in OAuth & Permissions, scroll up to OAuth Tokens for Your Workspace.
Click Install to Workspace and follow the prompts to authorize the app in your workspace.
Slack will provide an OAuth token after installation. Keep this token secure, as it will be used to authenticate your app’s API requests.
Save the slack signing secret from Basic Information page, it will be used by the bot.  
Save the oauth token from Oauth and permissions tab, this will also be used by the bot.
  
Verify Event Subscription (if not done already):

Slack will send a verification request to the Request URL you provided in Event Subscriptions. Make sure your endpoint responds to this with the challenge token sent by Slack to confirm the URL.

got to the channel and type /invite and choose app, to add it to the channel  

 curl -X POST -H "Authorization: Bearer xoxb-your-bot-token"      -H "Content-Type: application/json"      https://slack.com/api/auth.test | jq -r .user_id

get the bot user id using above command. this will used in main.py.
