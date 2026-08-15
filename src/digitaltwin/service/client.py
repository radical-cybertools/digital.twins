"""Client helper for the `dt` ORBIT plugin.

One synchronous class.  The shape a demo sees is the local `DTRuntime`
shape with a twin id in front::

    rt = EndpointRuntime(); rt.start(wait=True)

    dt   = rt.get_plugin('broker', 'dt', config=ENGINES)
    twin = dt.create_twin()                       # waits for 'ready'

    sensor = dt.package(MySensor)
    dt.add_task(twin, sensor, TRUTHY, SENSOR_DTYPE, is_persistent=True)
    dt.start(twin)
    ...
    dt.twin_close(twin)

The session survives the client: reattach later with
`rt.get_plugin('broker', 'dt', sid=<the sid>)` and the twins are still
running.
"""

import logging
import time
import uuid

from typing import Any, Optional

from radical.orbit.client import PluginClient

from ..components import DataType, TypedData
from .wire import (
    Package,
    decode,
    encode_checked,
    register_user_modules,
    version_stamp,
)

log = logging.getLogger("radical.orbit")

# how long `create_twin(wait=True)` polls for `ready` -- the service's
# background init is bounded well below this
CREATE_TIMEOUT = 300.0
POLL_INTERVAL = 0.5

# [P0-interim] large but finite; the transport's own call timeout (600 s
# by default, `EndpointRuntime(tuning={'call_timeout': …})`) caps it
INFERENCE_TIMEOUT = 600.0

READY_STATES = ("ready", "running", "stopped")


class DTClient(PluginClient):
    """Application-side API of the digital twin service."""

    # -- sessions -----------------------------------------------------------

    def register_session(
        self,
        sid: Optional[str] = None,
        lifetime: Optional[str] = None,
        ttl: Optional[float] = None,
        config: Optional[dict] = None,
        **kwargs: Any,
    ) -> None:
        """Open a session, or reattach to `sid`.

        `config` carries the engine configuration and applies at create
        time only::

            {"engines": {"task":   {"endpoint_name": "ep1",
                                    "backends": ["concurrent"]},
                         "exsitu": {"endpoint_name": "hpc1",
                                    "backends": ["concurrent"]}}}

        `'task'` runs the twins' components; `'exsitu'` runs the learner
        tasks of a `StreamingLearnerInvestigator` and aliases `'task'`
        when it is not configured.

        Sessions are always persistent (the service forces it), so a
        `lifetime` / `ttl` argument is accepted and ignored.
        """

        payload = {"sid": sid} if sid else {}
        if config is not None:
            payload["config"] = config

        resp = self._request("POST", self._url("register_session"), json=payload)
        self._raise(resp, "register_session")
        self._sid = resp.json()["sid"]

    def admin_sessions(self) -> dict:
        """Every session on this service, with its twins and their errors."""

        resp = self._request("GET", self._url("admin/sessions"))
        self._raise(resp, "admin_sessions")

        return resp.json()

    # -- artifacts ----------------------------------------------------------

    @staticmethod
    def package(cls: type, *args: Any, **kwargs: Any) -> Package:
        """Ship a component *class* plus its constructor arguments.

        The service instantiates it with the session's engine as the
        leading `flow` argument -- exactly the local constructor
        convention.  Classes defined outside an installed package need
        `register_user_modules([...])` first.
        """

        return Package(cls, args, kwargs)

    register_user_modules = staticmethod(register_user_modules)

    # -- twins --------------------------------------------------------------

    def create_twin(
        self,
        twin_id: Optional[str] = None,
        config: Optional[dict] = None,
        wait: bool = True,
        timeout: float = CREATE_TIMEOUT,
    ) -> str:
        """Create a twin and return its id.

        The id is a client-side uuid: re-issuing `create_twin` with the
        same id after a lost response is a no-op, which is what makes the
        one asynchronous verb safe to retry.

        The call itself returns as soon as the twin is registered
        (`initializing`); with `wait` the helper polls `twin_list` until
        the twin is `ready`.
        """

        twin_id = twin_id or str(uuid.uuid4())

        payload = {"twin_id": twin_id}
        if config is not None:
            payload["config"] = config

        resp = self._post(f"twin_create/{self.sid}", payload, "create_twin")
        if wait and resp["state"] not in READY_STATES:
            self.wait_ready(twin_id, timeout)

        return twin_id

    def wait_ready(self, twin_id: str, timeout: float = CREATE_TIMEOUT) -> str:
        """Poll `twin_list` until `twin_id` leaves `initializing`."""

        deadline = time.time() + timeout

        while True:
            twin = self.twin(twin_id)
            state = twin["state"]

            if state in READY_STATES:
                return state
            if state == "failed":
                raise RuntimeError(
                    f"twin {twin_id} failed to initialize: {twin['last_error']}"
                )
            if time.time() > deadline:
                raise TimeoutError(
                    f"twin {twin_id} still {state} after {timeout}s"
                )

            time.sleep(POLL_INTERVAL)

    def twin_list(self) -> list[dict]:
        """State of every twin in this session -- the observation path."""

        self._require_session()
        resp = self._request("GET", self._url(f"twin_list/{self.sid}"))
        self._raise(resp, "twin_list")

        return resp.json()["twins"]

    def twin(self, twin_id: str) -> dict:
        """One twin's entry from `twin_list`."""

        for twin in self.twin_list():
            if twin["twin_id"] == twin_id:
                return twin

        raise RuntimeError(f"unknown twin: {twin_id}")

    def twin_close(self, twin_id: str) -> str:
        """Stop and forget a twin.  A no-op on an already closed one."""

        return self._post(f"twin_close/{self.sid}/{twin_id}", None, "twin_close")[
            "state"
        ]

    # -- graph verbs --------------------------------------------------------

    def add_task(
        self,
        twin_id: str,
        package: Package,
        input_dtype: DataType,
        output_dtype: DataType,
        is_persistent: bool = False,
    ) -> str:
        return self._verb(
            twin_id, "add_task", package, input_dtype, output_dtype, is_persistent
        )["state"]

    def add_investigator(
        self,
        twin_id: str,
        package: Package,
        input_dtype: DataType,
        output_dtype: DataType,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        return self._verb(
            twin_id,
            "add_investigator",
            package,
            input_dtype,
            output_dtype,
            *args,
            **kwargs,
        )["state"]

    def add_agent(
        self,
        twin_id: str,
        package: Package,
        input_dtype: DataType,
        output_dtype: DataType,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        return self._verb(
            twin_id, "add_agent", package, input_dtype, output_dtype, *args, **kwargs
        )["state"]

    def start(self, twin_id: str) -> str:
        """Start a twin.  Starting a running twin is a no-op."""

        return self._verb(twin_id, "start")["state"]

    def stop(self, twin_id: str) -> str:
        """Stop a twin.  Terminal in v1, and a no-op once stopped."""

        return self._verb(twin_id, "stop")["state"]

    def describe(self, twin_id: str) -> dict:
        """The twin's serializable graph summary."""

        return self._verb(twin_id, "describe")["graph"]

    def get_inference(
        self,
        twin_id: str,
        in_data: TypedData,
        output_dtype: DataType,
        timeout: float = INFERENCE_TIMEOUT,
    ) -> TypedData:
        """Run one inference through the twin and return its result."""

        answer = self._verb(
            twin_id, "get_inference", in_data, output_dtype, timeout=timeout
        )

        return decode(answer["inference"])

    # -- transport ----------------------------------------------------------

    def _verb(self, twin_id: str, verb: str, *args: Any, **kwargs: Any) -> dict:
        """One graph verb, one request.

        Arguments are cloudpickled as a whole (dtypes, packages and
        inference payloads are all arbitrary Python) and size-checked
        against ORBIT's frame cap before they hit the wire.
        """

        payload = {
            "verb": verb,
            "payload": encode_checked({"args": args, "kwargs": kwargs},
                                      f"{verb} payload"),
            "client": version_stamp(),
        }

        return self._post(f"twin_call/{self.sid}/{twin_id}", payload, verb)

    def _post(self, path: str, payload: Optional[dict], context: str) -> dict:
        self._require_session()
        resp = self._request("POST", self._url(path), json=payload)
        self._raise(resp, context)

        return resp.json()
