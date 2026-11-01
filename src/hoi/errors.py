from shared.errors import HermesError


class OpportunityNotFound(HermesError):
    """Also returned when the caller is not on the deal team, so existence is not disclosed."""
    code = "opportunity_not_found"
    http_status = 404


class HoiConflict(HermesError):
    code = "hoi_conflict"
    http_status = 409


class HoiValidation(HermesError):
    code = "hoi_invalid"
    http_status = 422
