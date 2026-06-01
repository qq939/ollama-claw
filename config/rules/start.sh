#!/bin/bash
if [ -f user_start.sh ] && [ -s user_start.sh ]; then
    chmod +x user_start.sh
    ./user_start.sh
fi