from publish.permissions import HasCourseProviderAPIKey
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
)
from rest_framework import viewsets
from datetime import datetime
from django_scopes import scopes_disabled
from rest_framework.decorators import permission_classes
from campuslibs.refund.refund import Refund
from api_logging import ApiLogging


# Create your views here.
@permission_classes([HasCourseProviderAPIKey])
class RefundViewSet(viewsets.ModelViewSet):
    refund = Refund()
    http_method_names = ['post', 'head',]

    def get_queryset(self):
        fields = self.request.GET.copy()
        try:
            fields.pop("limit")
            fields.pop("page")
        except KeyError:
            pass

        return self.model.objects.filter(**fields.dict())

    def create(self, request, *args, **kwargs):
        log = ApiLogging()
        try:
            erp = request.course_provider.configuration.get('erp', '')
        except:
            erp = ''
        log_data = {
            'request': {
                'headers': request.headers,
                'body': request.data.copy()
            },
            'response': {
                'headers': request.headers,
                'body': {}
            }
        }

        status, data, message = self.refund.validate_refund_data(request)
        if not status:
            response = {
                "error": message,
                "status_code": 400,
            }
            log_data['response']['body'] = response
            log.store_logging_data(request, log_data, 'refund request-response from provider ' +
                                   request.course_provider.name, status_code=HTTP_400_BAD_REQUEST, erp=erp)
            return Response(
                response,
                status=HTTP_400_BAD_REQUEST,
            )

        status, response = self.refund.refund(request, data, requested_by='partner')
        if status:
            log_data['response']['body']['message'] = 'refund request placed successfully'
            log.store_logging_data(request, log_data, 'refund request-response from provider ' +
                                   request.course_provider.name, status_code=HTTP_200_OK, erp=erp)
            return Response({'message': 'refund request placed successfully'}, status=HTTP_200_OK)

        else:
            log_data['response']['body'] = response
            log.store_logging_data(request, log_data, 'refund request-response from provider ' +
                                   request.course_provider.name, status_code=HTTP_400_BAD_REQUEST, erp=erp)
            try:
                errors = response['transactionResponse']['errors']
            except Exception:
                return Response(
                    {
                        "error": {
                            "message": "something went wrong, please try again with correct information"
                        },
                        "status_code": 400,
                    },
                    status=HTTP_400_BAD_REQUEST,
                )
            else:
                for error in errors:
                    if error['errorCode'] == '54':
                        return Response(
                            {
                                "error": {
                                    "message": "Might not match required criteria for issuing a refund."
                                },
                                "status_code": 400,
                            },
                            status=HTTP_400_BAD_REQUEST,
                        )
                    elif error['errorCode'] == '11':
                        return Response(
                            {
                                "error": {
                                    "message": error['errorText']
                                },
                                "status_code": 400,
                            },
                            status=HTTP_400_BAD_REQUEST,
                        )

                else:
                    return Response(
                        {
                            "error": {
                                "message": errors[0]['errorText']
                            },
                            "status_code": 400,
                        },
                        status=HTTP_400_BAD_REQUEST,
                    )