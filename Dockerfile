# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy everything into /app
COPY . .

# Install required Python packages
RUN pip install websockets bcrypt

# Expose the port your server listens on
EXPOSE 9000

# Run the server
CMD ["python", "server.py"]


RUN pip install websockets bcrypt google-cloud-storage

