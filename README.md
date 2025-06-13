# SecureChat

## About
SecureChat is a chat system made for remote colleagues of the company, SecureTech Solutions. It uses WebSockets and is secure, convenient, and efficient for messaging. It is accessible here: https://chat-455.web.app/ (the app is offline now)
Watch video: 📺 [Watch Demo Video](https://youtu.be/i_Vd8bK311E?si=A0dvpieaxa6JWONM)

## How to use
To register: Make a username that has not been used before along with a password. Usernames can only have letters, numbers, and underscores. You usually can only make one registration within a 15 second period to prevent bot attacks. Your username and hashed password is then stored in a file for comparison in future logins.

To login: Provide your usernames and passwords after you register. 

To chat: Write your message in the message input box and press the button to the right of it to send. The user’s message should appear for the other user automatically. You can only make up to five messages within a twenty second period. A "Typing..." indicator will appear in the middle of the screen when the other user is typing. Chats are encrypted using AES and stored in a log in ciphertext. If a user sends you a message while you are not in their chatting screen, you will see a notification showcasing the number of unread messages. Clicking into their chatting screen removes this notification.

Status indicators: In the user list on the left (shows list of registered users), a black dot represents an offline user and a green dot represents an online user. 

To send files: Press the "Choose file" button to choose a file from your file explorer. After selecting your file, click "Share file". The file should appear as a downloadable link on the other side automatically. You can only send files that are no more than 15 MB. Script and executable files are blocked from sharing. 
This only works for small files. To share large files (but < 15 MB), we have hosted five files on Google Cloud to create public file links. They are:
1. Mars: https://storage.googleapis.com/securechat-filecloud-hosting/mars.jpg
2. Meme: https://storage.googleapis.com/securechat-filecloud-hosting/meme.jpg
3. Mountains: https://storage.googleapis.com/securechat-filecloud-hosting/moutains.jpg
4. Squid: https://storage.googleapis.com/securechat-filecloud-hosting/squid.jpg
5. Statue of Liberty: https://storage.googleapis.com/securechat-filecloud-hosting/statue.jpg

Simply copy and paste these links in the message input field and send.


Text formatting: To make bold text, do Ctrl + b and type. To make italicied text, do Ctrl + i and type. To make underlined text, do Ctrl + u and type. To make strikethrough text, do Ctrl + x and type. After you send your formatted message, you would have to do the control command again to send another specially formatted text. URL links are automatically shown as a clickable link on the other side. The sender just has to copy and paste the link into the message input field to send.

Emoji picker: Press the 😀 button which reveals a wide variety of emojis. Click on the emoji you want to send and it automatically appears in the message input field. Click "Send" to send the emoji.

To logout: On the upper right corner of the screen shows your username and the option to logout after you are done chatting.



