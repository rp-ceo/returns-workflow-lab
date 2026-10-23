from workflow import load_tickets


def sample(ticket_id):
    return next(ticket for ticket in load_tickets() if ticket["ticket_id"] == ticket_id)
