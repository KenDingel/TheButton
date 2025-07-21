# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install OS-level dependencies for fonts
RUN apt-get update && \
    apt-get install -y libfreetype6 libfontconfig1 && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
# This assumes 'assets/Mercy Christole.ttf' is in your build context
COPY . .

# To verify font is copied (optional, for debugging build):
# RUN ls -R /app/assets

# Run your bot
CMD ["python", "bot_code/theButton.py"]