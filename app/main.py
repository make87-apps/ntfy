import logging
from typing import Any
from urllib.parse import urlparse

import requests
from make87_messages.core.header_pb2 import Header
from make87_messages.primitive.bool_pb2 import Bool
import make87 as m87
from make87_ntfy.publish_pb2 import MessagePayload

from google.protobuf.json_format import MessageToDict


def ntfy_proto_to_dict(proto_message: MessagePayload) -> dict[str, Any]:
    """
    Converts a MessagePayload proto instance into a dictionary per the official schema.
    """
    message_dict = MessageToDict(proto_message, preserving_proto_field_name=True)

    # Convert priority enum to its integer value
    if "priority" in message_dict:
        message_dict["priority"] = proto_message.priority

    # Convert actions oneof field into expected format
    if "actions" in message_dict:
        for action in message_dict["actions"]:
            if "view" in action:
                action["action"] = "view"
                action["url"] = action.pop("view")["url"]
            elif "broadcast" in action:
                action["action"] = "broadcast"
                action["extras"] = action.pop("broadcast")["extras"]
            elif "http" in action:
                action["action"] = "http"
                http_fields = action.pop("http")
                action.update(http_fields)

    return message_dict


def main():
    m87.initialize()

    api_token = m87.get_config_value("NTFY_API_TOKEN", decode=str)
    post_url = m87.get_config_value("NTFY_URL", "https://ntfy.sh", decode=str)
    post_url = urlparse(post_url)
    post_url_base = f"{post_url.scheme}://{post_url.netloc}"
    post_url_path = post_url.path.removeprefix("/").removesuffix("/")

    endpoint = m87.get_provider(
        name="NOTIFICATION_SERVICE", requester_message_type=MessagePayload, provider_message_type=Bool
    )

    def callback(message: MessagePayload) -> Bool:
        post_dict = ntfy_proto_to_dict(message)
        if post_url_path:
            post_dict["topic"] = post_url_path

        response = requests.post(
            post_url_base,
            data=post_dict,  # Message body
            headers={
                "Authorization": f"Bearer {api_token}",
            },
        )

        header = Header()
        header.timestamp.GetCurrentTime()
        if response.ok:
            logging.info("Notification sent successfully.")
            return Bool(header=header, value=True)
        else:
            logging.error(f"Failed to send notification: {response.reason}")
            return Bool(header=header, value=False)

    endpoint.provide(callback)
    m87.loop()


if __name__ == "__main__":
    main()
