import asyncio
import websockets
import time
import signal
import sys
import json
import base64
import os
import bcrypt


USER_DB_FILE = "users.txt"

connected_users = {}
# In-memory storage for chat history (cleared when server restarts)
chat_storage = {}

# Rate limiting
limitOfMessages = 5  # Maximum number of messages per interval
rateLimSec = 20  # Time in seconds
user_message_log = {}  # Tracks user message timestamps for rate limiting

# Define lockout constants
failed_attempts = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_TIME = 20  # 5 minutes


# Load users from file
def load_users():
    users = {}
    if os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "r") as file:
            for line in file:
                parts = line.strip().split(" ")
                if len(parts) != 2:
                    continue  
                username, hashed_pw = parts
                users[username] = hashed_pw
    return users


# Save new user to file
def save_user(username, password):
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    with open(USER_DB_FILE, "a") as file:
        file.write(f"{username} {hashed_pw.decode()}\n")

 


async def handler(websocket):
    global failed_attempts
    stored_users = load_users()

    action = await websocket.recv()
     
    if action == "register":
        username = await websocket.recv()
        password = await websocket.recv()

        if username in stored_users:
            await websocket.send("REGISTER_FAILED: Username already exists.")
        else:
            save_user(username, password)
            await websocket.send("REGISTER_SUCCESS")
        return

    elif action == "login":
        username = await websocket.recv()
        password = await websocket.recv()


        # Check if user is locked out
        if username in failed_attempts and failed_attempts[username]["count"] >= MAX_FAILED_ATTEMPTS:
            time_since_last_attempt = time.time() - failed_attempts[username]["last_attempt"]
            if time_since_last_attempt < LOCKOUT_TIME:
                remaining_time = int(LOCKOUT_TIME - time_since_last_attempt)
                await websocket.send(f"LOCKOUT:{remaining_time}")
                await websocket.close()
                return
            else:
                failed_attempts[username]["count"] = 0  # Reset failed attempts after timeout

        
    # Authentication check using bcrypt
    if username in stored_users:
        stored_hashed_pw = stored_users[username].encode()
        if bcrypt.checkpw(password.encode(), stored_hashed_pw):
            failed_attempts[username] = {"count": 0, "last_attempt": time.time()}  

            if username not in connected_users:
                connected_users[username] = set()
            connected_users[username].add(websocket)

            print(f"{username} has connected.")

            # Send updated user list to all clients
            await broadcast_users_list()

            await websocket.send("Authentication successful. You can start chatting.")
            await send_chat_history_from_memory(websocket, username)
        else:
            # Invalid password
            if username not in failed_attempts:
                failed_attempts[username] = {"count": 1, "last_attempt": time.time()}
            else:
                failed_attempts[username]["count"] += 1
                failed_attempts[username]["last_attempt"] = time.time()

            remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts[username]["count"]
            await websocket.send(f"AUTH_FAILED:{remaining_attempts}")
            await websocket.close()
            return


    try:
        async for message in websocket:
            if message == "disconnecting":
                print(f"{username} has disconnected.")
                break

            if message.startswith("HISTORY_REQUEST:"):
                target_user = message.split(":")[1]
                await send_private_chat_history(websocket, username, target_user)
                continue

            if is_rate_limited(username):
                await websocket.send("Rate limit exceeded. Please wait before sending more messages.")
                continue  



       

            # Private message handling
            if message.startswith("@"):
                parts = message.split(" ", 1)
                if len(parts) > 1:
                    target_user = parts[0][1:]  
                    msg_content = parts[1]

                    if target_user in connected_users:
                        save_message_to_memory(username, target_user, msg_content)
                        for conn in connected_users[target_user]:
                            try:
                                await conn.send(f"{username}: {msg_content}")
                            except websockets.exceptions.ConnectionClosed:
                                continue

                        await websocket.send(f"{username}: {msg_content}")
                    else:
                        await websocket.send(f"Error: {target_user} is not online.")
                else: 
                    await websocket.send("Invalid message format. Use @username message")
            else:
                # Broadcast message to all users
                for user, conn in connected_users.items():
                    if user != username:
                        try:
                            await conn.send(f"{username}: {message}")
                        except websockets.exceptions.ConnectionClosed:
                            del connected_users[user]
                

    # Remove user on disconnect
    finally:
        
        if username in connected_users:
            connected_users[username].discard(websocket)
            if not connected_users[username]:
                del connected_users[username]
            await broadcast_users_list()




# Save messages to in-memory storage
def save_message_to_memory(sender, receiver, message):
    chat_id = f"{sender}_{receiver}" if sender < receiver else f"{receiver}_{sender}"

    if chat_id not in chat_storage:
        chat_storage[chat_id] = []  # Initialize chat storage for this conversation

    chat_storage[chat_id].append(f"{sender}: {message}")  # Store message in memory

# Retrieve chat history from memory
async def send_chat_history_from_memory(websocket, username):
    for chat_id, messages in chat_storage.items():
        if username in chat_id:
            for msg in messages:
                await websocket.send(msg)




# Rate-limiting function
def is_rate_limited(username):
    current_time = time.time()
    
    if username not in user_message_log:
        user_message_log[username] = []

    # Remove old timestamps
    user_message_log[username] = [
        timestamp for timestamp in user_message_log[username]
        if timestamp > current_time - rateLimSec
    ]

    if len(user_message_log[username]) >= limitOfMessages:
        return True

    user_message_log[username].append(current_time)
    return False
 


# Function to send private chat history between two users
async def send_private_chat_history(websocket, username, target_user):
    chat_id = f"{username}_{target_user}" if username < target_user else f"{target_user}_{username}"

    if chat_id in chat_storage:
        for msg in chat_storage[chat_id]:
            await websocket.send(msg)


async def broadcast_users_list():
    user_list = ",".join(connected_users.keys())
    for conns in connected_users.values():
        for conn in conns:
            try:
                await conn.send(f"USERS:{user_list}")
            except websockets.exceptions.ConnectionClosed:
                continue





async def tellClients(message):
    # Sends a message to all clients notifying them what occurred.
    for user, conn in connected_users.items():
        try:
            await conn["websocket"].send(message)
        except websockets.exceptions.ConnectionClosed:
            continue  # Clients no longer connected are ignored.

async def fileTransfer(username, message):
    try:
        filejson = json.loads(message.decode())  # bytes decoded to json
        fileName = filejson["name"]
        fileData = base64.b64decode(filejson["data"])  



        with open(fileName, "wb") as file:
            file.write(fileData)


        print(f"{username} has sent file: {fileName}")


        # Notify all users and send file data
        for user, conn in connected_users.items():
            if user != username:  # File doesn't get sent to sender
                try:
                    await conn["websocket"].send(json.dumps({
                        "type": "file",
                        "name": fileName,
                        "data": filejson["data"]  # Base64 data sent
                    }))
                except websockets.exceptions.ConnectionClosed:
                    continue
    except Exception as e:
        print(f"File error: {e}")


# Graceful server shutdown
async def shutServer(server):
    print("Shutting down server...")
    
    global chat_storage
    chat_storage.clear()  # Clear all chat history

    # Notify and close all WebSocket connections
    tasks = []
    for user, conn in list(connected_users.items()):
        try:
            tasks.append(conn.send("Server is shutting down..."))
            tasks.append(conn.close())  # Close each WebSocket
        except websockets.exceptions.ConnectionClosed:
            continue  

    await asyncio.gather(*tasks, return_exceptions=True)  # Ensure all close operations complete
    connected_users.clear()

    # Close WebSocket server
    server.close()
    await server.wait_closed()

    print("Chat history cleared. Server successfully shut down.")


async def main():
    print("Starting WebSocket server on ws://localhost:9000")

    async def handler_wrapper(*args):
        return await handler(args[0])

    server = await websockets.serve(handler_wrapper, "localhost", 9000)

    stop_event = asyncio.Event()

    def shutDown(signal_received, frame):
        print("Received shutdown signal...")

        loop = asyncio.get_running_loop()

        # Schedule server shutdown
        task = asyncio.create_task(shutServer(server))

        # Stop the loop after shutdown completes
        task.add_done_callback(lambda t: loop.call_soon_threadsafe(loop.stop))
    
    signal.signal(signal.SIGINT, shutDown)  
    signal.signal(signal.SIGINT, shutDown)  

    await stop_event.wait()  


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down...")