#!/usr/bin/env bash
read payload
cd /var/www/sosmark.ru
git fetch origin main
git reset --hard origin/main
systemctl restart myapp.service
