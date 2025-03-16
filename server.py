import asyncio
import websockets
import time
import signal
import sys
import secrets

connected_users = {}
stored_users = {
    "user1": "ABC123",
    "user2": "XYZ789",
    "user3": "COM",

}  
# In-memory storage for chat history (cleared when server restarts)
chat_storage = {}


# Rate limiting
limitOfMessages = 5  # Maximum number of messages per interval
rateLimSec = 20  # Time in seconds
user_message_log = {}  # Tracks user message timestamps for rate limiting


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
  


async def handler(websocket):
    username = None  # To prevent errors if user disconnects early
    try:
        username = await websocket.recv()
        password = await websocket.recv()

        if username in stored_users and password == stored_users[username]:
            connected_users[username] = websocket
            print(f"{username} has connected.")

            # Send updated user list to all clients
            await broadcast_users_list()

            await websocket.send("Authentication successful. You can start chatting.")
            await send_chat_history_from_memory(websocket, username)  # Load chat history on login

            async for message in websocket:
                if message == "disconnecting":
                    print(f"{username} has disconnected.")
                    break


                # Handle chat history request when switching users
                if message.startswith("HISTORY_REQUEST:"):
                    target_user = message.split(":")[1]
                    chat_id = f"{username}_{target_user}" if username < target_user else f"{target_user}_{username}"

                    if chat_id in chat_storage:
                        for msg in chat_storage[chat_id]:
                            await websocket.send(msg)
                    continue

                # Rate-limiting check
                if is_rate_limited(username):
                    await websocket.send("Rate limit exceeded. Please wait before sending more messages.")
                    continue  

                # Handle private messages     
                if message.startswith("@"):  # Private message format: @user message
                    parts = message.split(" ", 1)
                    if len(parts) > 1:
                        target_user = parts[0][1:]  # Remove '@' from username
                        msg_content = parts[1]

                        if target_user in connected_users:
                            try:
                                save_message_to_memory(username, target_user, msg_content)  # Save chat in memory
                                await connected_users[target_user].send(f"{username}: {msg_content}")
                            except websockets.exceptions.ConnectionClosed:
                                del connected_users[target_user]
                    else:
                        await websocket.send("Invalid message format. Use @username message")
                else:
                    await websocket.send("To send a message, use @recipient_username message_content.")

        else:
            await websocket.send("Authentication failed. Invalid username or password.")
            await websocket.close()

    except websockets.exceptions.ConnectionClosed:
        print(f"{username} has disconnected.")
    finally:
        if username and username in connected_users:
            del connected_users[username]
            await broadcast_users_list()


async def broadcast_users_list():
    """Sends an updated list of connected users to all clients."""
    user_list = ",".join(connected_users.keys())  # Convert list to comma-separated string
    for user in connected_users.values():
        await user.send(f"USERS:{user_list}")



async def tellClients(message):
    # Sends a message to all clients notifying them what occurred.
    for user, conn in connected_users.items():
        try:
            await conn["websocket"].send(message)
        except websockets.exceptions.ConnectionClosed:
            continue  # Clients no longer connected are ignored.


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