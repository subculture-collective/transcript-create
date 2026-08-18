from worker.vocabulary import apply_vocabulary_corrections, load_vocabularies


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Connection:
    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        rows = self.rows
        if rows is None:
            rows = [{"id": params["vocabulary_ids"][0], "name": "Selected", "terms": []}]
        return _Result(rows)


def test_worker_loads_exactly_selected_accessible_vocabularies():
    connection = _Connection()

    rows = load_vocabularies(connection, "owner-1", ["vocab-2"])

    assert [row["id"] for row in rows] == ["vocab-2"]
    assert len(connection.calls) == 1
    sql, params = connection.calls[0]
    assert "is_global = true OR user_id = :user_id" in sql
    assert params == {"vocabulary_ids": ["vocab-2"], "user_id": "owner-1"}


def test_worker_loads_nothing_when_job_selected_no_vocabularies():
    connection = _Connection()

    assert load_vocabularies(connection, "owner-1", []) == []
    assert connection.calls == []


def test_worker_fails_if_a_selected_vocabulary_disappeared():
    connection = _Connection(rows=[])

    try:
        load_vocabularies(connection, "owner-1", ["vocab-deleted"])
    except ValueError as error:
        assert "unavailable" in str(error)
    else:
        raise AssertionError("missing selected vocabulary must fail the worker stage")


def test_archive_vocabulary_corrects_recurring_hasanabi_intro_without_job_selection():
    connection = _Connection()
    segments = [
        {
            "start": 952.0,
            "end": 960.0,
            "text": (
                "fantastic evening, afternoon, pre-new. I'm a Sompiker. "
                "And this thoughts and I'm broadcast. All the boys, girls and MPs. "
                "We condemn Hassan Hassan Habib Piker."
            ),
        }
    ]

    corrected = apply_vocabulary_corrections(connection, segments, None, [])

    assert corrected[0]["text"] == (
        "fantastic evening, afternoon, pre-noon. I'm Hasan Piker. "
        "And this is the HasanAbi broadcast. All the boys, girls and Enbies. "
        "We condemn Hasan HasanAbi Piker."
    )
    assert corrected[0]["start"] == 952.0
    assert connection.calls == []


def test_archive_vocabulary_corrects_recurring_guest_names():
    segments = [{"text": "Oliver Largan spoke with Amela Keros."}]

    corrected = apply_vocabulary_corrections(_Connection(), segments, None, [])

    assert corrected[0]["text"] == "Oliver Larkin spoke with Melat Kiros."
