# websocket-app

## About
SecureChat is a chat system made for remote colleagues of the company, SecureTech Solutions. It uses WebSockets and is secure, convenient, and efficient enough for messaging.

## How to use and test?
To login: Provide your usernames and passwords. The usernames for the two users are “user1” and “user2”. The password for both users is “password”. After logging in, messages notifying of connection will be displayed to the users and in the server as well.

To chat: Write your message in the text box and press the button to the right of it to send. The user’s message should appear for the other user. It will also appear in the server terminal.

To test rate limiting: The users are only limited to making five messages within a twenty second period. Making more messages in a twenty second interval would bring up a message saying that you are posting too much. Look at the other user’s window to see if the “spamming” messages came through. They are not expected to go to the other user because of rate limiting.

To test disconnection detection: Press the logout button for one of the users. Go to the other user that is still connected. You will see a message for that still-connected user that the disconnected user has disconnected. Go to the server and you will see that message as well.

To test automatic reconnection after interruption: Turn off the server by doing Ctrl+C in server terminal. You will see a message that the server is shutting down. Go to the user windows and you will see that for both users, there is a notification that there is an interruption. Restart the server to end the interruption, and you will see that both users automatically connect. You can now continue to send messages.

