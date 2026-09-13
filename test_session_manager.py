import os
import tempfile

from data_loader import rename_account_in_csv
import session_manager as sm


def test_rename_account_profile_moves_credentials_and_session():
    with tempfile.TemporaryDirectory() as d:
        sm.DATA_DIR = d
        sm.ACCOUNTS_FILE = os.path.join(d, "sc_accounts.enc")
        sm.SESSION_STATE_FILE = os.path.join(d, "sc_session.json")

        assert sm.save_account_profile("old", "a@example.com", "secret")
        old_session = sm._session_file_for("old")
        with open(old_session, "w", encoding="utf-8") as f:
            f.write("{}")

        assert sm.rename_account_profile("old", "new")
        assert not sm.has_saved_credentials("old")
        assert sm.has_saved_credentials("new")
        assert not os.path.exists(old_session)
        assert os.path.exists(sm._session_file_for("new"))


def test_rename_account_in_csv_updates_profile_columns_only():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "data.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write("site_location,account_profile,question\nA,old,Q1\nB,other,Q2\nC,old,Q3\n")

        assert rename_account_in_csv(path, "old", "new") == 2

        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
        assert "A,new,Q1" in text
        assert "B,other,Q2" in text
        assert "C,new,Q3" in text


if __name__ == "__main__":
    test_rename_account_profile_moves_credentials_and_session()
    test_rename_account_in_csv_updates_profile_columns_only()
