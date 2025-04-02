#!/bin/bash

bot(){
    python3 main.py
}

until bot; do
    echo "'main.py' crashed with exit code $?. Restarting..." >&2
    sleep 1
done