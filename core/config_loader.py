from pathlib import Path
import yaml


CONFIG_PATH = Path("config/app.yaml")


def load_config():
    with open(CONFIG_PATH, "r") as file:
        return yaml.safe_load(file)


if __name__ == "__main__":
    config = load_config()

    print("Loaded configuration:")
    print(config)
