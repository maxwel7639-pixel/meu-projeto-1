from agente import create_web_app

app = create_web_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
