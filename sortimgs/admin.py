from django.contrib import admin

from .models import ImageSet, Label, Image, Annotation, User
from django.db.models import Count
import csv
from django.http import HttpResponse
from django.http import StreamingHttpResponse
from pathlib import Path
#from admin_thumbnails.thumbnail import AdminThumbnail

import datetime

@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ['name', 'imageset']
    list_filter = ['imageset']

@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
#    list_display = ['file_path', 'image_set', 'image_tag']
    list_display = ['file_path', 'image_set']
    list_filter = ['image_set']
#    readonly_fields = ['image_tag']

def generate_csv_stream(separator = ';', image_set=None):
    """
    Generator function to stream CSV data
    """
    header_row = ['Image Name'] + [user.username for user in User.objects.all()]
    yield(separator.join(header_row) + '\n')

    # write data row
    images = Image.objects.filter(image_set=image_set)
    for image in images:

        ext = Path(image.file_path).name.split('.')[-2]
        row = [Path(image.file_path).stem.split('___')[0] + '.' +  ext]
        annotations = Annotation.objects.filter(image=image)

        annotation_dict = {}
        for annotation in annotations:
            annotation_dict[annotation.user.username] = annotation.label.name

        # Write the label name of the Annotation for each user (leave blank if not present)
        for user in User.objects.all():
            user_label = annotation_dict.get(user.username, '')
            row.append(user_label)

        yield(separator.join(row) + '\n')


@admin.register(ImageSet)
class ImageSetAdmin(admin.ModelAdmin):
    list_display = ['name', 'image_count']
    actions = ['export_as_csv']

    def image_count(self, obj):
        return obj.images.count()
    image_count.short_description = 'Images Count'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(Count('images'))
        return queryset

    def export_as_csv(self, request, queryset):
        """
        Export all rabeling data for each user by csv (semi-colon)
        """
        csv_generator = generate_csv_stream(separator=';', image_set=queryset[0])
        response = StreamingHttpResponse(csv_generator, content_type='text/csv')
        current_datetime = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        response['Content-Disposition'] = f'attachment; filename="image_set{queryset[0]}_{current_datetime}.csv"'
        return response


    export_as_csv.short_description = 'Export as CSV'
