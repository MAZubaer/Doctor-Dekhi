"""The text shown at the top of Swagger UI and Scalar."""

API_DESCRIPTION = """
Patients at public hospitals in Bangladesh often arrive before dawn to stand in a
serial line, with no idea when the doctor will see them. Doctor Dekhi lets a patient
book a serial and follow the queue from a phone, with no account needed, while
hospital staff run the same queue from the counter.

## Try it in 2 minutes

Each hospital has an **Emergency duty session open around the clock**, with a queue
already in progress, so this works at any hour. Use **Try it out** on each route
below, and copy IDs from the responses, because they change between deployments.

1. **Find a hospital.** Run `GET /hospitals` and copy the `id` of Dhaka Medical
   College Hospital. Then run `GET /hospitals/{hospital_id}/departments` and copy the
   `id` of **Emergency**.
2. **Find a doctor.** Run `GET /doctors/available` with that `department_id` and copy
   the `schedule_id`.
3. **Book a serial.** Run `POST /serials`, replacing the example `schedule_id` with
   yours. Use a made-up mobile number, because a number can only hold one active
   serial per session. Copy the `id` from the response.
4. **Check your place.** Run `GET /serials/{serial_id}/status` with that `id`.
5. **Authorize as staff.** Select **Authorize** at the top of this page and log in as
   `01700000012` with password `Demo@1234`. Other fields can stay empty.
6. **Call the next patient.** Run `POST /staff/schedules/{schedule_id}/next` with the
   same `schedule_id`.
7. **Check your place again.** Repeat step 4. The queue has moved and you are closer
   to your turn.

## Demo logins

The password for every account is `Demo@1234`. Enter the phone number as `username`.

| Role | Phone | Hospital |
| --- | --- | --- |
| Super admin | `01700000001` | All hospitals |
| Hospital admin | `01700000011` | Dhaka Medical College Hospital |
| Staff | `01700000012` | Dhaka Medical College Hospital |
| Hospital admin | `01800000011` | Chattogram Medical College Hospital |
| Staff | `01800000012` | Chattogram Medical College Hospital |

All SMS messages are mocked: they are saved to the database and written to the
server log, and nothing is sent.
"""

OPENAPI_TAGS = [
    {
        "name": "Patient",
        "description": (
            "Find a doctor, book a serial and follow the queue. No login is needed: "
            "a patient is identified by their phone number."
        ),
    },
    {
        "name": "Auth",
        "description": "Staff login with a phone number and password, returning a bearer token.",
    },
    {
        "name": "Staff",
        "description": (
            "Run a hospital's queues. Requires a login, and staff can only reach their "
            "own hospital. Only admins can change a schedule's availability."
        ),
    },
    {
        "name": "System",
        "description": "API information and the health check.",
    },
]
