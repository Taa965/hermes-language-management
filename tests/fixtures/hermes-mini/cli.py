def main() -> None:
    print("Welcome to Hermes Agent")
    print("Start a new session")
    answer = input("Choice [y/N]: ")
    if answer.lower().startswith("y"):
        print("Saved to config.yaml")


def retry_status(error_name: str, provider: str, delay: int) -> dict[str, str]:
    status_message = (
        f"Transient {error_name} on {provider} - rebuilt client, waiting {delay}s before one last primary attempt."
    )
    return {"message": status_message}


if __name__ == "__main__":
    main()
