FROM python:3.9.16-slim

WORKDIR /usr/src/bot

COPY requirements.txt ./
RUN pip install --upgrade pip
#RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --user -r requirements.txt
RUN rm -rf requirements.txt

COPY . .

CMD [ "python", "bot.py", "run"]