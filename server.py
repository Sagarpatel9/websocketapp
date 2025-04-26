import asyncio
import websockets
import time
import signal
import sys
import json
import base64
import os
import bcrypt
import traceback
import datetime


USER_DB_FILE = "users.txt"
LOG_FOLDER = "wss_logs"

if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)

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
shutting_down = False




# Load users from file
def load_users():
    users = {}
    if os.path.exists(USER_DB_FILE):
        with open(USER_DB_FILE, "r", encoding='utf-8') as file: 
            for line in file:
                parts = line.strip().split(" ", 1) 
                if len(parts) == 2:
                    username, hashed_pw = parts
                    if username and hashed_pw: 
                        users[username] = hashed_pw
                
    return users

def new_log():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logFile = os.path.join(LOG_FOLDER, f"chat-{timestamp}.txt")
    return logFile

def msgRec(logFile, sender, message):
   
    with open(logFile, 'a') as file:
        file.write(f'{sender} -> {message}\n')


# Save new user to file
def save_user(username, password):
    
    try:
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()) 
        with open(USER_DB_FILE, "a", encoding='utf-8') as file: 
            file.write(f"{username} {hashed_pw.decode('utf-8')}\n")
    except Exception as e:
         print(f"!!! Error saving user {username}: {e} !!!")

 
async def handler(websocket):
    global failed_attempts, connected_users, chat_storage, user_message_log, shutting_down
    username = None 
    login_username_attempt = None
    try:
        stored_users = load_users()
        action = await websocket.recv()

        if action == "register":
            # Use distinct variable names for registration
            reg_username = await websocket.recv()
            reg_password = await websocket.recv()

            
            if not reg_username or not reg_password or ' ' in reg_username:
                 await websocket.send("REGISTER_FAILED: Invalid username or password.")
                 
                 return 

            if reg_username in stored_users:
                await websocket.send("REGISTER_FAILED: Username already exists.")
            else:
                save_user(reg_username, reg_password)
                await websocket.send("REGISTER_SUCCESS")
            
            return 

        elif action == "login":
            # Use a specific variable for the login attempt
            login_username_attempt = await websocket.recv()
            password = await websocket.recv()

            if not login_username_attempt or not password:
                await websocket.send("AUTH_FAILED:N/A")
                return 

            
            if login_username_attempt in failed_attempts and \
               failed_attempts[login_username_attempt]["count"] >= MAX_FAILED_ATTEMPTS:
                time_since_last_attempt = time.time() - failed_attempts[login_username_attempt]["last_attempt"]
                if time_since_last_attempt < LOCKOUT_TIME:
                    remaining_time = int(LOCKOUT_TIME - time_since_last_attempt)
                    await websocket.send(f"LOCKOUT:{remaining_time}")
                    
                    return 
                else:
                    
                    failed_attempts[login_username_attempt] = {"count": 0, "last_attempt": time.time()}

            # --- Authentication check ---
            if login_username_attempt in stored_users:
                stored_hashed_pw = stored_users[login_username_attempt].encode('utf-8') 
                if bcrypt.checkpw(password.encode('utf-8'), stored_hashed_pw):
                    # --- Login Success ---
                    username = login_username_attempt 
                    
                    failed_attempts.pop(username, None) 

                    if username not in connected_users:
                        connected_users[username] = set()
                    connected_users[username].add(websocket)

                    print(f"{username} has connected.") 

                    await broadcast_users_list()
                    await websocket.send("Authentication successful. You can start chatting.")
                    await send_chat_history_from_memory(websocket, username)
                    # --- Continue to message loop ---

                else:
                    # --- Invalid password ---
                    if login_username_attempt not in failed_attempts:
                        failed_attempts[login_username_attempt] = {"count": 0, "last_attempt": 0.0}
                    failed_attempts[login_username_attempt]["count"] += 1
                    failed_attempts[login_username_attempt]["last_attempt"] = time.time()

                    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts[login_username_attempt]["count"]
                    await websocket.send(f"AUTH_FAILED:{remaining_attempts}")
                    
                    return 
            else:
                # --- User Not Found ---
                print(f"Login attempt for non-existent user: {login_username_attempt}")
                await websocket.send(f"AUTH_FAILED:N/A") 
                
                return 
        else:
             # --- Unknown Action ---
             print(f"Unknown action received: {action}") 
             await websocket.close(code=1003, reason="Unsupported action")
             return 

        # --- Safety check after login/register logic ---
        if not username:

             print(f"!!! Error: Logic flow error. No username assigned after action '{action}'. Closing connection. !!!")
             return 

        msgList = []

        try:
            # --- Message Loop ---
            async for message in websocket:
                # --- Basic Message Validation ---
                if not isinstance(message, str):
                    print(f"Warning: Received non-string message from '{username}'. Type: {type(message)}. Ignoring.")
                    continue

                if message == "disconnecting":
                    print(f"{username} has disconnected.")
                    break

                # --- Chat History Request ---
                if message.startswith("HISTORY_REQUEST:"):
                    parts = message.split(":", 1)
                    if len(parts) == 2 and parts[1]:
                        target_user = parts[1]
                        await send_private_chat_history(websocket, username, target_user)
                    else:
                        await websocket.send("Invalid HISTORY_REQUEST format. Use HISTORY_REQUEST:target_username")
                    continue
        
                # --- Rate Limit Check ---
                if is_rate_limited(username):
                    await websocket.send("Rate limit exceeded. Please wait before sending more messages.")
                    continue
        
                # --- Private Message Handling ---
                if message.startswith("@"):
                    parts = message.split(" ", 1)
                    if len(parts) > 1 and parts[0][1:]:
                        target_user = parts[0][1:]
                        msg_content = parts[1]
        
                        if target_user == username:
                            await websocket.send("Cannot send private message to yourself.")
                            continue
        
                        msgTime = time.time()
                        msgList.append((username, message, msgTime))
        
                        if target_user in connected_users:
                            save_message_to_memory(username, target_user, msg_content)
                            formatted_msg = f"{username}: {msg_content}"
        
                            for conn in list(connected_users[target_user]):
                                try:
                                    await conn.send(formatted_msg)
                                except websockets.exceptions.ConnectionClosed:
                                    print(f"Warning: Send failed to closed connection for '{target_user}'.")
                                    continue
                                except Exception as send_error:
                                    print(f"!!! Error sending PM to '{target_user}': {send_error} !!!")
        
                            await websocket.send(formatted_msg)
                        else:
                            await websocket.send(f"Error: {target_user} is not online.")
                    else:
                        await websocket.send("Invalid message format. Use @username message")
                else:
                    # --- Broadcast Message Handling ---
                    broadcast_msg = f"{username}: {message}"
                    msgTime = time.time()
                    msgList.append((username, message, msgTime))
        
                    recipients = []
                    for user, connections in connected_users.items():
                        if user != username:
                            recipients.extend(list(connections))
        
                    if not recipients:
                        continue
        
                    results = await asyncio.gather(
                        *[conn.send(broadcast_msg) for conn in recipients],
                        return_exceptions=True
                    )
        
                    for i, result in enumerate(results):
                        if isinstance(result, websockets.exceptions.ConnectionClosed):
                            failed_conn = recipients[i]
                            print(f"Warning: Broadcast failed to closed connection {failed_conn.remote_address}.")
                        elif isinstance(result, Exception):
                            failed_conn = recipients[i]
                            print(f"!!! Error broadcasting to {failed_conn.remote_address}: {result} !!!")

        except websockets.exceptions.ConnectionClosedOK:
            pass
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"Connection closed with error for {username or 'user'} ({websocket.remote_address}): {e}")
        except asyncio.CancelledError:
            print(f"Task cancelled for {username or 'user'} ({websocket.remote_address})")
        except Exception as e:
            print(f"!!! UNEXPECTED Error in handler for {username or 'user'} ({websocket.remote_address}): {e} !!!")
            traceback.print_exc()
        
        # --- Cleanup ---
        finally:
            if username and username in connected_users:
                if websocket in connected_users[username]:
                    connected_users[username].discard(websocket)
                if not connected_users[username]:
                    print(f"{username} (last connection) has disconnected.")
                    del connected_users[username]
                    await broadcast_users_list()
        
            try:
                await websocket.close()
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as close_err:
                print(f"!!! Error during final websocket close: {close_err} !!!")
        
            # --- Logging Messages ---
            sessionLog = new_log()
            orderedList = sorted(msgList, key=lambda x: x[2])
            for sender, msg, _ in orderedList:
                msgRec(sessionLog, sender, msg)

    except Exception as outer_error:
        print(f"!!! Outer error in handler for {websocket.remote_address}: {outer_error} !!!")
        traceback.print_exc()



# Save messages to in-memory storage
def save_message_to_memory(sender, receiver, message):
    chat_id = f"{sender}_{receiver}" if sender < receiver else f"{receiver}_{sender}"
    if chat_id not in chat_storage:
        chat_storage[chat_id] = []  # Initialize chat storage for this conversation
    chat_storage[chat_id].append(f"{sender}: {message}")  # Store message in memory


# Retrieve chat history from memory
async def send_chat_history_from_memory(websocket, username):
    sent_any = False
    for chat_id, messages in list(chat_storage.items()): 
        if f"_{username}" in chat_id or f"{username}_" in chat_id:
            for msg in list(messages): 
                 try:
                     await websocket.send(msg)
                     sent_any = True
                 except websockets.exceptions.ConnectionClosed:
                      print(f"Warning: Connection closed during initial history send to {username}.")
                      return 
                 except Exception as e:
                      print(f"!!! Error sending history msg to {username}: {e} !!!")




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
    
    
    chat_id = "_".join(sorted([username, target_user]))
    if chat_id in chat_storage:
        for msg in list(chat_storage[chat_id]): 
            try:
                await websocket.send(msg)
            except websockets.exceptions.ConnectionClosed:
                print(f"Warning: Connection closed sending private history between {username} and {target_user}.")
                break
            except Exception as e:
                 print(f"!!! Error sending private history msg to {username}: {e} !!!")
                 
    


async def broadcast_users_list():
    
    user_list = ",".join(sorted(connected_users.keys())) 
    connections_to_send = [conn for conn_set in connected_users.values() for conn in conn_set]

    # Use gather for concurrent sending
    results = await asyncio.gather(
        *[conn.send(f"USERS:{user_list}") for conn in connections_to_send],
        return_exceptions=True
    )
    for i, res in enumerate(results):
         if isinstance(res, Exception):
              failed_conn = connections_to_send[i]


async def tellClients(message):
    
    connections_to_tell = [conn for conn_set in connected_users.values() for conn in conn_set]
    for conn in connections_to_tell:
        try: await conn.send(message) 
        except: continue  


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
            if user != username:  
                try:
                    await conn["websocket"].send(json.dumps({
                        "type": "file",
                        "name": fileName,
                        "data": filejson["data"]  
                    }))
                except websockets.exceptions.ConnectionClosed:
                    continue
    except Exception as e:
        print(f"File error: {e}")


async def shutServer(server, stop_event):
    global shutting_down
    if shutting_down:
        return  
    shutting_down = True

    print("Shutting down server...")

    global chat_storage
    chat_storage.clear()  

    tasks = []
    for user, connections in list(connected_users.items()):  
        for conn in connections:  
            try:
                tasks.append(conn.send("Server is shutting down..."))  
                tasks.append(conn.close())  
            except websockets.exceptions.ConnectionClosed:
                continue  

    await asyncio.gather(*tasks, return_exceptions=True) 
    connected_users.clear()  

    server.close()
    await server.wait_closed()

    print("Chat history cleared. Server successfully shut down.")
    
    stop_event.set()  



shutting_down = False  


async def main():
    global shutting_down
    print("Starting WebSocket server on ws://localhost:9000")

    stop_event = asyncio.Event()


    server = await websockets.serve(handler, "localhost", 9000)

    def shutDown(signal_received, frame):
        global shutting_down
        if shutting_down:
            return  
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(asyncio.create_task, shutServer(server, stop_event))  

    signal.signal(signal.SIGINT, shutDown)  

    try:
        await stop_event.wait()  
    finally:
        await shutServer(server, stop_event) 


if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        pending = asyncio.all_tasks(loop)
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(asyncio.sleep(1))  # Allow tasks to finish
        loop.close()