import logging
from urllib.parse import urlparse

import make87
import requests
from google.protobuf.json_format import MessageToDict
from make87_messages.core.header_pb2 import Header
from make87_messages.primitive.bool_pb2 import Bool
from make87_ntfy.publish_pb2 import MessagePayload


def ntfy_proto_to_request_components(proto_message):
    """
    Converts a MessagePayload proto instance into a dictionary of headers.

    Returns:
        tuple: (topic, message, headers_dict)
    """
    # Convert proto to dictionary while preserving field names
    message_dict = MessageToDict(proto_message, preserving_proto_field_name=True)

    # Extract topic and message if available
    topic = message_dict.get("topic", None)
    message = message_dict.get("message", None)

    # Prepare headers
    headers = {}

    # Process all other fields into headers
    for key, value in message_dict.items():
        if key in ["topic", "message", "actions", "header"]:
            continue  # Skip these as they are handled separately, or not at all

        header_key = f"X-{key.capitalize()}"  # Capitalize first letter
        if key == "priority":  # Convert enum name to integer
            headers[header_key] = str(proto_message.priority)
        elif isinstance(value, list):  # Convert lists to comma-separated values
            headers[header_key] = ",".join(map(str, value))
        elif isinstance(value, bool):  # Convert booleans to lowercase strings
            headers[header_key] = str(value).lower()
        else:
            headers[header_key] = str(value)

    # Handle actions separately
    if "actions" in message_dict:
        action_headers = []
        for action in message_dict["actions"]:
            label = action.get("label", "Unknown")
            clear = action.get("clear", "false")  # Default to false
            if "view" in action:
                action_headers.append(f"view, {label}, {action['view']['url']}, clear={clear}")
            elif "broadcast" in action:
                extras = ",".join([f"{k}={v}" for k, v in action["broadcast"]["extras"].items()])
                action_headers.append(f"broadcast, {label}, {extras}, clear={clear}")
            elif "http" in action:
                http_fields = action["http"]
                method = http_fields.get("method", "GET")
                url = http_fields.get("url", "Unknown")
                headers_str = ",".join([f"{k}={v}" for k, v in http_fields.get("headers", {}).items()])
                body = http_fields.get("body", "")
                action_headers.append(
                    f"http, {label}, {method} {url}, headers={headers_str}, body={body}, clear={clear}"
                )

        headers["X-Actions"] = "; ".join(action_headers)

    return topic, message, headers


def main():
    make87.initialize()

    api_token = make87.get_config_value("NTFY_API_TOKEN", decode=str)
    post_url = make87.get_config_value("NTFY_URL", "https://ntfy.sh", decode=str)
    post_url = urlparse(post_url)
    post_url_base = f"{post_url.scheme}://{post_url.netloc}"
    post_url_path = post_url.path.removeprefix("/").removesuffix("/")

    endpoint = make87.get_provider(
        name="NOTIFICATION_SERVICE", requester_message_type=MessagePayload, provider_message_type=Bool
    )

    def callback(message: MessagePayload) -> Bool:
        nonlocal post_url_path, post_url_base

        topic, message, headers = ntfy_proto_to_request_components(message)

        if not post_url_path and topic is not None:
            post_url_path = topic

        response = requests.post(
            f"{post_url_base}/{post_url_path}",
            data=message.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_token}",
                **headers,
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
    make87.loop()


if __name__ == "__main__":
    main()
