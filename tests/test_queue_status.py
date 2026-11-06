"""A patient checks their place in the queue. Schedules here use 10 minutes per patient."""

from tests.factories import DONE, MISSED, SERVING, WAITING


def status_of(client, serial) -> dict:
    response = client.get(f"/serials/{serial.id}/status")
    assert response.status_code == 200, response.text
    return response.json()


def test_people_ahead_ignores_missed_patients(client, factory):
    schedule = factory.schedule()
    *_, last = factory.queue(schedule, WAITING, MISSED, WAITING, WAITING)

    status = status_of(client, last)

    assert status["people_ahead"] == 2
    assert status["estimated_wait_minutes"] == 20
    assert status["message"] == "2 people ahead of you."


def test_wait_includes_the_patient_being_served(client, factory):
    schedule = factory.schedule()
    _, serving, next_patient, last = factory.queue(schedule, DONE, SERVING, WAITING, WAITING)

    status = status_of(client, last)
    assert status["now_serving"] == 2
    assert status["people_ahead"] == 1
    assert status["estimated_wait_minutes"] == 20

    status = status_of(client, next_patient)
    assert status["people_ahead"] == 0
    assert status["estimated_wait_minutes"] == 10
    assert status["message"] == "You are next in the queue."

    status = status_of(client, serving)
    assert status["estimated_wait_minutes"] == 0
    assert status["message"] == "It's your turn now."


def test_waiting_patient_is_on_hold_until_the_schedule_reopens(client, factory, db):
    schedule = factory.schedule()
    serving, waiting = factory.queue(schedule, SERVING, WAITING)
    assert status_of(client, waiting)["is_on_hold"] is False

    schedule.is_available = False
    db.commit()

    on_hold = status_of(client, waiting)
    assert on_hold["is_on_hold"] is True
    assert on_hold["estimated_wait_minutes"] is None
    assert on_hold["message"] == "Doctor is unavailable right now. Your serial is on hold."
    assert on_hold["status"] == "waiting"
    assert status_of(client, serving)["is_on_hold"] is False

    schedule.is_available = True
    db.commit()

    reopened = status_of(client, waiting)
    assert reopened["is_on_hold"] is False
    assert reopened["estimated_wait_minutes"] == 10
