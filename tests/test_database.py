from database import Database


def test_initialize_and_idempotent_insert(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    inserted, duplicates = database.insert_transactions(
        [("2025-01-01", "Sales", 12.5, "Order")]
    )
    repeated, repeated_duplicates = database.insert_transactions(
        [("2025-01-01", "Sales", 12.5, "Order")]
    )

    assert (inserted, duplicates) == (1, 0)
    assert (repeated, repeated_duplicates) == (0, 1)
    assert len(database.fetch_transactions()) == 1


def test_fetch_transactions_filters_inclusive_dates(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    database.insert_transactions(
        [
            ("2025-01-01", "Sales", 10, ""),
            ("2025-01-02", "Sales", 20, ""),
            ("2025-01-03", "Sales", 30, ""),
        ]
    )

    assert len(database.fetch_transactions("2025-01-02", "2025-01-02")) == 1
