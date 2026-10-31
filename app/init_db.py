from app.database import DATABASE_PATH, initialize_database


def main() -> None:
    initialize_database()
    print(f"GullyScore database initialized: {DATABASE_PATH}")


if __name__ == "__main__":
    main()
