"""Fixed Switch QA operations; room messages are never executed as shell code."""
import argparse
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import urlparse

SOURCE = Path(__file__).resolve().parents[1]
WORKSPACE = SOURCE.parent
sys.path.insert(0, str(SOURCE))

from intent_replay.qa_room import QaRoomStore, RoomError
from intent_replay.qa_room_switch import SwitchClient, SwitchDispatcher, load_config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=WORKSPACE / ".local/qa-room/connection.json")
    parser.add_argument("--state", type=Path, default=WORKSPACE / ".local/qa-room/state")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("serve", help="Serve validated local evidence; no review mutations.")
    commands.add_parser("probe", help="Verify the configured local Switch connection; no room posts.")
    inspect = commands.add_parser("show", help="Read local stored evidence/status without approving it.")
    inspect.add_argument("--run-id")
    dispatch = commands.add_parser("dispatch", help="Fetch one authentic Switch message and perform its fixed QA operation.")
    dispatch.add_argument("--message-id", required=True)
    setup = commands.add_parser("configure", help="Write private path/identity references after Console room setup.")
    setup.add_argument("--gateway-url", required=True)
    setup.add_argument("--room-id", required=True)
    setup.add_argument("--agent-id", required=True)
    setup.add_argument("--agent-name", default="intent-replay-qa")
    setup.add_argument("--task-id", default="booking-withdrawal")
    setup.add_argument("--native-env-file", type=Path, required=True)
    setup.add_argument("--agent-credentials-file", type=Path, required=True)
    setup.add_argument("--report-url", default="http://127.0.0.1:8054")
    args = parser.parse_args(argv)
    try:
        if args.operation == "configure":
            if args.config.exists():
                raise RoomError("configuration_exists", "Existing configuration is preserved; explicitly edit its nonsecret references if needed.")
            config = {"gateway_url":args.gateway_url,"room_id":args.room_id,"agent_id":args.agent_id,
                      "agent_name":args.agent_name,"task_id":args.task_id,"report_url":args.report_url,
                      "native_env_file":str(args.native_env_file.resolve()),
                      "agent_credentials_file":str(args.agent_credentials_file.resolve())}
            client = SwitchClient(config)
            try:
                client.login()
                identity = client._json("GET", "/gateway/auth/me")
                config["reviewer_user_ids"] = [identity["id"]]
                config["reviewer_client_ids"] = []
                config["observed_server"] = client.observed_server
                # Confirm configured room membership through its supported read API.
                client._json("GET", "/gateway/chats/" + args.room_id + "/messages", params={"limit":1})
            finally:
                client.close()
            args.config.parent.mkdir(parents=True,exist_ok=True)
            with args.config.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(config,stream,indent=2)
                stream.write("\n")
            load_config(args.config)
            print(json.dumps({"configured":str(args.config),"room_id":args.room_id,
                              "observed_server":config["observed_server"],"credentials_copied":False}))
            return 0
        config = load_config(args.config)
        if args.operation == "serve":
            import uvicorn
            from intent_replay.qa_room_http import create_app
            address = urlparse(config["report_url"])
            if not address.port:
                raise RoomError("invalid_configuration", "The report URL must include its local listener port.")
            store = QaRoomStore(args.state / "workflow")
            # A managed provider needs only this bounded local operation, not
            # permission to launch a shell or receive server/agent credentials.
            token_path = args.config.parent / "dispatch-token"
            try:
                with token_path.open("x", encoding="utf-8") as token_file:
                    token_file.write(secrets.token_urlsafe(32) + "\n")
            except FileExistsError:
                pass
            token = token_path.read_text(encoding="utf-8").strip()
            if len(token) < 32:
                raise RoomError("invalid_configuration", "The private local dispatch token is invalid.")

            def dispatch_original(message_id):
                client = SwitchClient(config)
                try:
                    return SwitchDispatcher(config,args.state,client=client).dispatch(message_id,post=True)
                finally:
                    client.close()

            app = create_app(store,room_id=config["room_id"],task_id=config["task_id"],
                             agent_mention="@"+config["agent_name"],
                             dispatch_message=dispatch_original,dispatch_token=token)
            print("QA evidence: " + config["report_url"] + "/qa/current",flush=True)
            uvicorn.run(app,host=address.hostname,port=address.port,access_log=False,log_level="warning")
            return 0
        if args.operation == "show":
            result = QaRoomStore(args.state / "workflow").show_run(config["room_id"],config["task_id"],args.run_id)
        else:
            client = SwitchClient(config)
            try:
                if args.operation == "probe":
                    client.login()
                    identity=client._json("GET", "/gateway/auth/me")
                    result={"connected":True,"observed_server":client.observed_server,"reviewer_identity_matches":identity["id"] in config["reviewer_user_ids"],
                            "room_id":config["room_id"],"provider_inference_requested":False}
                else:
                    result=SwitchDispatcher(config,args.state,client=client).dispatch(args.message_id,post=True)
            finally:
                client.close()
        print(json.dumps(result,indent=2))
        return 0 if result.get("ok",True) else 1
    except RoomError as exc:
        print(json.dumps({"ok":False,"error_code":exc.code,"message":str(exc)}))
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        # Never print credentials or untrusted network/configuration error bodies.
        print(json.dumps({"ok":False,"error_code":"configuration_or_storage_error",
                          "message":"Check private configuration references and local state; no review was granted."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
