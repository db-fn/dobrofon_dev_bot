FROM python:3.11.0

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app to move .env file etc.
COPY . /app

RUN pip install --upgrade pip
RUN apt-get update
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
