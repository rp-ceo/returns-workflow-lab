"""Response templates. The classifier never writes customer-facing replies."""


def request_reference(language):
    if language == "es":
        return (
            "Por favor, envíanos el número de pedido para que podamos revisar "
            "tu solicitud."
        )
    return "Please share your order reference so we can check your request."


def tracking_update(order, language):
    reference = order["order_id"]
    tracking = order["tracking_reference"]
    if language == "es":
        status = "en tránsito" if order["status"] == "in_transit" else "entregado"
        return (
            f"El estado del pedido {reference} es {status}. "
            f"Referencia de seguimiento de prueba: {tracking}."
        )
    status = order["status"].replace("_", " ")
    return f"Order {reference} is {status}. Demo tracking reference: {tracking}."


def return_instructions(reference, language):
    if language == "es":
        return (
            f"El pedido {reference} cumple las comprobaciones iniciales de nuestra "
            "política de prueba. Confirma qué artículo quieres devolver y su estado "
            "para que el equipo pueda indicarte los siguientes pasos. "
            "Aún no se ha emitido ninguna etiqueta ni reembolso."
        )
    return (
        f"Order {reference} passes the initial checks in our demo return policy. "
        "Please confirm the item and its condition so the team can provide the "
        "next steps. No label or refund has been issued."
    )
