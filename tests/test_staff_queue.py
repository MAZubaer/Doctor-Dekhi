"""Staff run a queue: calling patients, walk-ins, missed patients and cancellations."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.models import NotificationType, SerialSource, UserRole
from tests.factories import DONE, MISSED, SERVING, WAITING, assert_error, serial_nos_notified

STAFF = UserRole.STAFF
ADMIN = UserRole.HOSPITAL_ADMIN
SUPER_ADMIN = UserRole.SUPER_ADMIN


def call_next(client, schedule, headers, **body):
    return client.post(f"/staff/schedules/{schedule.id}/next", headers=headers, json=body or None)


def set_availability(client, schedule, headers, is_available: bool):
    return client.patch(
        f"/staff/schedules/{schedule.id}/availability",
        headers=headers,
        json={"is_available": is_available},
    )


def statuses(client, schedule, headers) -> dict[int, str]:
    response = client.get(f"/staff/schedules/{schedule.id}/queue", headers=headers)
    assert response.status_code == 200, response.text
    return {entry["serial_no"]: entry["status"] for entry in response.json()}


def test_staff_cannot_reach_another_hospitals_queue(client, factory, login_as):
    other_hospital = factory.hospital("Chattogram Medical College Hospital")
    schedule = factory.schedule(other_hospital)
    serving, waiting = factory.queue(schedule, SERVING, WAITING)
    own_hospital = factory.hospital()
    own_schedule = factory.schedule(own_hospital)
    headers = login_as(ADMIN, own_hospital)
    url = f"/staff/schedules/{schedule.id}"
    walk_in = {"patient_name": "Rokeya Begum", "phone": "01812345678"}

    attempts = [
        client.get(f"{url}/queue", headers=headers),
        client.post(f"{url}/next", headers=headers),
        client.post(f"{url}/walk-in", headers=headers, json=walk_in),
        client.patch(f"{url}/availability", headers=headers, json={"is_available": False}),
        client.post(f"/staff/serials/{waiting.id}/missed", headers=headers),
        client.get(f"/staff/schedules?hospital_id={other_hospital.id}", headers=headers),
    ]

    for response in attempts:
        assert_error(response, 403, "HOSPITAL_ACCESS_DENIED")
    assert statuses(client, schedule, login_as(SUPER_ADMIN)) == {1: "serving", 2: "waiting"}
    listed = client.get("/staff/schedules", headers=headers).json()
    assert [row["schedule_id"] for row in listed] == [own_schedule.id]


def test_super_admin_can_run_queues_in_any_hospital(client, factory, login_as):
    first = factory.schedule(factory.hospital())
    second = factory.schedule(factory.hospital("Chattogram Medical College Hospital"))
    factory.queue(first, WAITING)
    factory.queue(second, WAITING)
    headers = login_as(SUPER_ADMIN)

    schedules = client.get("/staff/schedules", headers=headers).json()

    assert {row["schedule_id"] for row in schedules} == {first.id, second.id}
    assert call_next(client, first, headers).status_code == 200
    assert call_next(client, second, headers).status_code == 200


def test_call_next_serves_patients_in_order_and_skips_missed(client, factory, login_as):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    factory.queue(schedule, SERVING, MISSED, WAITING, WAITING)
    headers = login_as(STAFF, hospital)

    response = call_next(client, schedule, headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["finished_serial"]["serial_no"] == 1
    assert body["serving_serial"]["serial_no"] == 3
    assert body["current_serial"] == 3
    assert body["message"] == "Now serving serial #3."
    assert body["counts"] == {"waiting": 1, "serving": 1, "done": 1, "missed": 1}
    assert statuses(client, schedule, headers) == {
        1: "done", 2: "missed", 3: "serving", 4: "waiting",
    }


def test_last_call_finishes_the_queue_and_then_it_is_empty(client, factory, login_as):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    factory.queue(schedule, DONE, SERVING)
    headers = login_as(STAFF, hospital)

    finished = call_next(client, schedule, headers)

    assert finished.status_code == 200, finished.text
    assert finished.json()["message"] == "Queue finished. No patients are waiting."
    assert finished.json()["serving_serial"] is None
    assert_error(call_next(client, schedule, headers), 400, "QUEUE_EMPTY")


def test_expected_serial_blocks_a_stale_call_and_allows_a_current_one(
    client, factory, login_as
):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    factory.queue(schedule, DONE, SERVING, WAITING)
    headers = login_as(STAFF, hospital)

    response = call_next(client, schedule, headers, expected_current_serial=1)

    body = assert_error(response, 409, "QUEUE_CHANGED")
    assert body["details"] == {"expected_current_serial": 1, "current_serial": 2}
    assert statuses(client, schedule, headers) == {1: "done", 2: "serving", 3: "waiting"}

    response = call_next(client, schedule, headers, expected_current_serial=2)

    assert response.status_code == 200, response.text
    assert response.json()["current_serial"] == 3


def test_double_click_calls_only_one_patient(client, factory, login_as):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    factory.queue(schedule, SERVING, WAITING, WAITING)
    headers = login_as(STAFF, hospital)
    start_together = Barrier(2)

    def click(_):
        start_together.wait()
        return call_next(client, schedule, headers, expected_current_serial=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(click, range(2)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert statuses(client, schedule, headers) == {1: "done", 2: "serving", 3: "waiting"}


def test_turn_near_goes_to_the_nearest_patients_once_each(client, factory, db, login_as):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    factory.queue(schedule, *[WAITING] * 6)
    headers = login_as(STAFF, hospital)

    call_next(client, schedule, headers)
    assert serial_nos_notified(db, schedule, NotificationType.TURN_NEAR) == [2, 3, 4]

    call_next(client, schedule, headers)
    assert serial_nos_notified(db, schedule, NotificationType.TURN_NEAR) == [2, 3, 4, 5]

    call_next(client, schedule, headers)
    call_next(client, schedule, headers)
    assert serial_nos_notified(db, schedule, NotificationType.TURN_NEAR) == [2, 3, 4, 5, 6]


def test_turn_near_reaches_a_patient_who_jumps_ahead_after_a_missed(
    client, factory, db, login_as
):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    serials = factory.queue(schedule, SERVING, *[WAITING] * 5)
    serial_3, serial_5 = serials[2], serials[4]
    headers = login_as(STAFF, hospital)
    call_next(client, schedule, headers)  # Serves #2. Waiting: #3 #4 #5 #6, and #6 is 4th.
    assert serial_nos_notified(db, schedule, NotificationType.TURN_NEAR) == [3, 4, 5]

    client.post(f"/staff/serials/{serial_3.id}/missed", headers=headers)
    client.post(f"/staff/serials/{serial_5.id}/missed", headers=headers)
    assert serial_nos_notified(db, schedule, NotificationType.TURN_NEAR) == [3, 4, 5]

    call_next(client, schedule, headers)  # Serves #4, so #6 jumps straight to next.

    assert serial_nos_notified(db, schedule, NotificationType.TURN_NEAR) == [3, 4, 5, 6]


def test_walk_in_takes_the_next_serial_and_records_the_staff_member(
    client, factory, db, login
):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    factory.queue(schedule, SERVING, WAITING)
    staff = factory.user(STAFF, hospital)
    body = {"patient_name": "Rokeya Begum", "phone": "+8801812345678"}
    headers = login(staff)

    response = client.post(f"/staff/schedules/{schedule.id}/walk-in", headers=headers, json=body)

    assert response.status_code == 201, response.text
    assert response.json()["serial_no"] == 3
    assert response.json()["source"] == SerialSource.WALK_IN
    assert response.json()["phone"] == "018****5678"
    queue = client.get(f"/staff/schedules/{schedule.id}/queue", headers=headers).json()
    assert queue[-1]["created_by"] == staff.id
    assert queue[-1]["phone"] == "01812345678"
    assert serial_nos_notified(db, schedule, NotificationType.CONFIRMATION) == [3]


@pytest.mark.parametrize("final_status", [DONE, MISSED], ids=["done", "missed"])
def test_finished_patients_cannot_be_marked_missed(client, factory, login_as, final_status):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    [serial] = factory.queue(schedule, final_status)

    response = client.post(
        f"/staff/serials/{serial.id}/missed", headers=login_as(STAFF, hospital)
    )

    body = assert_error(response, 400, "INVALID_STATUS_TRANSITION")
    assert body["details"] == {"from": final_status, "to": "missed"}


def test_plain_staff_cannot_change_availability(client, factory, db, login_as):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)

    response = set_availability(client, schedule, login_as(STAFF, hospital), False)

    assert_error(response, 403, "FORBIDDEN_ROLE")
    db.refresh(schedule)
    assert schedule.is_available is True


@pytest.mark.parametrize("role", [ADMIN, SUPER_ADMIN])
def test_cancelling_notifies_waiting_patients_once_and_stops_the_queue(
    client, factory, db, login_as, role
):
    hospital = factory.hospital()
    schedule = factory.schedule(hospital)
    factory.queue(schedule, DONE, SERVING, MISSED, WAITING, WAITING)
    headers = login_as(role, hospital if role is ADMIN else None)

    response = set_availability(client, schedule, headers, False)

    assert response.status_code == 200, response.text
    assert response.json()["is_available"] is False
    assert response.json()["patients_notified"] == 2
    assert serial_nos_notified(db, schedule, NotificationType.CANCELLED) == [4, 5]

    repeat = set_availability(client, schedule, headers, False)
    assert repeat.json()["patients_notified"] == 0
    assert serial_nos_notified(db, schedule, NotificationType.CANCELLED) == [4, 5]

    assert_error(call_next(client, schedule, headers), 400, "SCHEDULE_NOT_ACTIVE")
