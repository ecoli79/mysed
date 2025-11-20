from django.db import models
from mayan.apps.documents.models import Document
from django.contrib.auth import get_user_model

User = get_user_model()

class DocumentDeadline(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='deadlines')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='document_deadlines')
    deadline = models.DateField()
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.document} - {self.user} - {self.deadline}'