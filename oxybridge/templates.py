from oxybridge.db import uid


def order_template():
    names = [
        "Incoming order",
        "Validate order",
        "Order value > 500?",
        "Priority fulfillment",
        "Standard fulfillment",
        "Prepare reservation",
        "Inventory API",
        "Store order",
        "Send callback",
    ]
    kinds = [
        "webhook",
        "validate",
        "condition",
        "set",
        "set",
        "transform",
        "http",
        "postgres",
        "callback",
    ]
    positions = [
        (380, 20),
        (380, 155),
        (380, 290),
        (170, 440),
        (590, 440),
        (380, 595),
        (380, 730),
        (380, 865),
        (380, 1000),
    ]
    aliases = [
        "incoming",
        "validation",
        "value_check",
        "priority",
        "standard",
        "reservation",
        "inventory",
        "store",
        "callback",
    ]
    configs = [
        {},
        {
            "input": "{{ trigger.body }}",
            "schema": {
                "type": "object",
                "required": ["order_id", "total", "customer"],
                "properties": {
                    "order_id": {"type": "string"},
                    "total": {"type": "number", "minimum": 0},
                    "customer": {
                        "type": "object",
                        "required": ["email"],
                        "properties": {"email": {"type": "string"}},
                    },
                },
            },
        },
        {"left": "{{ trigger.body.total }}", "operator": "greater", "right": 500},
        {"mapping": {"order_id": "{{ trigger.body.order_id }}", "priority": "high", "vip": True}},
        {
            "mapping": {
                "order_id": "{{ trigger.body.order_id }}",
                "priority": "standard",
                "vip": False,
            }
        },
        {
            "mapping": {
                "order_id": "{{ trigger.body.order_id }}",
                "customer": "{{ trigger.body.customer }}",
                "total": "{{ trigger.body.total }}",
                "source": "OxyBridge",
                "priority": "{{ vars.priority }}",
                "vip": "{{ vars.vip }}",
            }
        },
        {
            "method": "POST",
            "url": "https://postman-echo.com/post",
            "body": "{{ nodes.reservation.output }}",
            "timeout": 15,
            "retry": {
                "max_attempts": 3,
                "initial_delay": 2,
                "multiplier": 2,
                "max_delay": 30,
                "jitter": True,
            },
        },
        {
            "query": "INSERT INTO orders (order_id, total) VALUES (%(order_id)s, %(total)s) ON CONFLICT (order_id) DO UPDATE SET total = EXCLUDED.total RETURNING order_id",
            "parameters": {
                "order_id": "{{ trigger.body.order_id }}",
                "total": "{{ trigger.body.total }}",
            },
            "mode": "write",
            "connection_id": "",
        },
        {
            "method": "POST",
            "url": "https://postman-echo.com/post",
            "body": {"order_id": "{{ trigger.body.order_id }}", "status": "reserved"},
            "timeout": 15,
        },
    ]
    nodes = [
        {
            "id": uid(),
            "type": kind,
            "label": name,
            "alias": alias,
            "position": {"x": x, "y": y},
            "config": config,
        }
        for name, kind, alias, (x, y), config in zip(names, kinds, aliases, positions, configs)
    ]
    links = [
        (0, 1, "success"),
        (1, 2, "valid"),
        (2, 3, "true"),
        (2, 4, "false"),
        (3, 5, "success"),
        (4, 5, "success"),
        (5, 6, "success"),
        (6, 7, "success"),
        (7, 8, "success"),
    ]
    edges = [
        {"id": uid(), "source": nodes[a]["id"], "target": nodes[b]["id"], "sourceHandle": handle}
        for a, b, handle in links
    ]
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def routing_template():
    definition = order_template()
    definition["nodes"] = definition["nodes"][:6]
    ids = {n["id"] for n in definition["nodes"]}
    definition["edges"] = [e for e in definition["edges"] if e["target"] in ids]
    return definition


def templates():
    manual, transform, http = uid(), uid(), uid()
    return [
        {
            "id": "order-routing",
            "name": "Order routing",
            "description": "Validate incoming orders, choose a fulfillment priority, and prepare a reservation.",
            "category": "Operations",
            "definition": routing_template(),
            "sample": {
                "order_id": "ORD-2041",
                "total": 749,
                "customer": {"email": "customer@example.com"},
            },
        },
        {
            "id": "order-fulfillment",
            "name": "Order Fulfillment Demo",
            "description": "Order routing, inventory API, parameterized PostgreSQL storage, and a callback. Select a write-enabled database connection and configure your API URLs.",
            "category": "Integrations",
            "definition": order_template(),
            "sample": {
                "order_id": "ORD-2041",
                "total": 749,
                "customer": {"email": "customer@example.com"},
            },
        },
        {
            "id": "api-pipeline",
            "name": "API request pipeline",
            "description": "Map a sample payload and send it to a REST API with bounded retries.",
            "category": "APIs",
            "sample": {"customer": {"email": "customer@example.com"}, "amount": 120},
            "definition": {
                "schema_version": 1,
                "nodes": [
                    {
                        "id": manual,
                        "type": "manual",
                        "label": "Manual trigger",
                        "alias": "start",
                        "position": {"x": 100, "y": 80},
                        "config": {},
                    },
                    {
                        "id": transform,
                        "type": "transform",
                        "label": "Map customer",
                        "alias": "customer",
                        "position": {"x": 100, "y": 240},
                        "config": {
                            "mapping": {
                                "email": "{{ trigger.body.customer.email }}",
                                "amount": "{{ trigger.body.amount }}",
                            }
                        },
                    },
                    {
                        "id": http,
                        "type": "http",
                        "label": "Send to API",
                        "alias": "response",
                        "position": {"x": 100, "y": 400},
                        "config": {
                            "method": "POST",
                            "url": "https://postman-echo.com/post",
                            "body": "{{ nodes.customer.output }}",
                            "timeout": 15,
                        },
                    },
                ],
                "edges": [
                    {"id": uid(), "source": manual, "target": transform, "sourceHandle": "success"},
                    {"id": uid(), "source": transform, "target": http, "sourceHandle": "success"},
                ],
            },
        },
    ]
