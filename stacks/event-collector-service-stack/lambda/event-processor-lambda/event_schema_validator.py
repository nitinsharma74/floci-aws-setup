class EventSchemaValidator:
    SCHEMA = {
        'eventType': str,
        'eventId': str,
        'transactionId': str,
        'accountId': str,
        'cardId': str,
        'merchantId': str,
        'transactionType': str,
        'channel': str,
        'amount': (int, float),
        'currency': str,
        'country': str,
        'deviceId': str,
        'ipAddress': str,
        'timestamp': str,
        'expectedFraud': bool,
    }

    def validate(self, event):
        errors = []

        for field, expected_type in self.SCHEMA.items():
            if field not in event:
                errors.append(f'Missing required field: {field}')
                continue

            if not isinstance(event[field], expected_type):
                errors.append(f'Invalid type for {field}: expected {self._type_name(expected_type)}, got {type(event[field]).__name__}')

        if isinstance(event.get('amount'), (int, float)) and event['amount'] < 0:
            errors.append('amount must be greater than or equal to 0')

        return errors

    def tag(self, event):
        errors = self.validate(event)
        event['schemaStatus'] = 'invalid' if errors else 'valid'
        event['schemaErrors'] = errors
        return event

    def _type_name(self, expected_type):
        if isinstance(expected_type, tuple): return ' or '.join(value.__name__ for value in expected_type)
        return expected_type.__name__