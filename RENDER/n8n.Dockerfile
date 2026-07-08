FROM n8nio/n8n:latest

# Render provides PORT automatically. n8n listens on 5678 by default.
EXPOSE 5678

# Start n8n
CMD ["n8n"]