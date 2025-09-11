
from django.utils.datastructures import MultiValueDictKeyError
from django.shortcuts import render, redirect
from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.urls import reverse
from django.http import StreamingHttpResponse

from .models import ImageSet, Image, Label, Annotation, User
from .forms import ImageForm

from pathlib import Path
import random
import datetime
import PIL
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile

from .admin import generate_csv_stream

import os
import zipfile


class ImageSetListView(LoginRequiredMixin, generic.ListView):
    model = ImageSet
    template_name = 'sortIT/imageset_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        labels = Label.objects.filter(imageset__in=context['object_list']).select_related('imageset')
        label_dict = {}

        for label in labels:
            label_dict.setdefault(label.imageset, []).append(label)

        context['label_dict'] = label_dict
        return context

@login_required
def choose_img_set(request):
    try:
        imagesets = ImageSet.objects.all()

        if not imagesets:
            return redirect('/admin/sortIT/imageset/add/')
            # return redirect('sortIT:finish') # ここで別のページにリダイレクトする

    except Exception as e:
        print(f'Error fetching ImageSets: {e}')
        return redirect('/admin/sortIT/imageset/add/')

    labels = Label.objects.filter(imageset__in=imagesets).select_related('imageset')
    label_dict = {}

    for label in labels:
        label_dict.setdefault(label.imageset, []).append(label)

    context = {'object_list': imagesets, 'label_dict': label_dict}
    return render(request, 'sortIT/imageset_list.html', context)



# Multiple Choice Mode
@staff_member_required
def labeling(request, image_set_id):
    
    # get specified image set
    image_set = ImageSet.objects.get(id=image_set_id)

    images = image_set.images.all()
    labels = image_set.label_set.all()


    # Check the number of labels linked to the ImageSet
    if labels.count() == 1 or (labels.count() == 2 and labels.filter(name='other').exists()):
        # And Redirect to sortOne View if there is ONLY ONE label other than "other" label
        return redirect('sortIT:sortone', image_set_id=image_set_id)


    # Choose un-labeled images randomly
    unlabeled_images = images.exclude(annotations__user=request.user)
    if unlabeled_images:
        image = random.choice(unlabeled_images)
    else:
        return redirect('sortIT:finish')

    # Calculate progress
    total_images = images.count()
    labeled_images = total_images - unlabeled_images.count()
    progress = round(labeled_images / total_images * 100)

    # Show labeling form
    context = {
        'image': image,
        'labels': labels,
        'image_set': image_set,
        'progress': progress,
        'n_total': total_images,
        'n_labeled': labeled_images,
    }
    return render(request, 'sortIT/labeling.html', context)

@staff_member_required
def label_post(request):
    # Get the image and label selected by the user
    image_id = request.POST.get('image')
    label_id = request.POST.get('label')
    if image_id and label_id:
        image = Image.objects.get(id=image_id)
        label = Label.objects.get(id=label_id)

        # Create an Annotation object
        annotation = Annotation(image=image, label=label, user=request.user)
        annotation.save()

        # Redirect to the same ImageSet
        return redirect('sortIT:labeling', image.image_set.id)
    else:
        # if the image or label is not specified
        return HttpResponse('Please select an image and a label.')


@staff_member_required
def sortone(request, image_set_id):

    # get specified image set
    image_set = ImageSet.objects.get(id=image_set_id)

    # Get images and labels linked to the ImageSet
    images = image_set.images.all()
    labels = image_set.label_set.all()

    # Check the number of labels linked to the ImageSet
    if not (labels.count() == 1 or (labels.count() == 2 and labels.filter(name='other').exists())):
        # And Redirect to usual labeling mode View if there are > 2 labels
        return redirect('sortIT:labeling', image_set_id=image_set_id)

    # count total number of images
    total_images = images.count()

    # Get the label linked to the ImageSet that is not "other"
    label = labels.exclude(name='other').first()

    # Create the "other" label if it is not registered in the ImageSet
    if not labels.filter(name='other').exists():
        other_label = Label.objects.create(imageset=image_set, name='other')
    else:
        other_label = labels.get(name='other')

    # Choose un-sorted images
    unsorted_images = images.exclude(annotations__user=request.user)
    if unsorted_images:
        # number of images to show
        n_images = 36
        # Randomly select n_images
        images = random.sample(list(unsorted_images), min(n_images, unsorted_images.count()))
    else:
        # If all images are sorted, redirect to finish
        return redirect('sortIT:finish')

    # Calculate progress
    n_labeled = total_images - unsorted_images.count()
    progress = round(n_labeled / total_images * 100)

    # Show sorting form
    context = {
        'images': images,
        'label': label,
        'image_set': image_set,
        'progress': progress,
        'n_total': total_images,
        'n_labeled': n_labeled,
    }
    return render(request, 'sortIT/sortone.html', context)

@staff_member_required
def sort_post(request):
    if request.method == 'POST':
        image_set_id = request.POST['image_set']
        selected_images = request.POST['selected_images'].split(',')

        image_set = ImageSet.objects.get(id=image_set_id)
        labels = image_set.label_set.all()

        # Get 'non-other' label which linked to the image-set
        label = labels.exclude(name='other').first()

        # Create "other label" if not present
        if not labels.filter(name='other').exists():
            other_label = Label.objects.create(imageset=image_set, name='other')
        else:
            other_label = labels.get(name='other')

        # Get all image id displayed
        displayed_images = request.POST['displayed_images'].split(',')

        # Add "label" to the selected images, "other_label" to the unselected images
        for image_id in displayed_images:
            image = Image.objects.get(id=image_id)
            if image_id in selected_images:
                Annotation.objects.create(image=image, label=label, user=request.user)
            else:
                Annotation.objects.create(image=image, label=other_label, user=request.user)

        # Redirect to the next page
        return redirect('sortIT:sortone', image_set_id=image_set_id)


def finish(request):
    return render(request, 'sortIT/thankyou.html')

@login_required
def show_image(request, image_id):
    image = Image.objects.get(id=image_id)
    response = FileResponse(open(image.file_path, 'rb'))
    return response


def write_file(img_dst, jpeg_img):
    with open(img_dst, 'wb+') as dst:
        for chunk in jpeg_img.chunks():
            dst.write(chunk)



def process_image(img, image_set_id):
    with BytesIO() as img_io:
        img_io.write(img.read())
        img_io.seek(0)

        with PIL.Image.open(img_io) as pil_img:
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")

            width, height = pil_img.size
            max_size = (700, 700)
            if width > max_size[0] or height > max_size[1]:
                pil_img.thumbnail(max_size)

            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

            with BytesIO() as output_io:

                try:

                    # if the image size is > 20KB save image with quality 75 to save the storage
                    if img_io.tell() < 20 * 1024:
                        quality = 100
                    else:
                        quality = 75

                    pil_img.save(output_io, format='JPEG', quality=quality)
                    output_io.seek(0)

                    jpeg_img = InMemoryUploadedFile(output_io, 'ImageField', img.name, 'image/jpeg', output_io.tell(), None)
                    imgname = Path(img._get_name())
                    ext = imgname.name.split('.')[-1]

                    now = datetime.datetime.now()
                    time = now.strftime("%Y%m%d-%H%M%S")

                    fname = f'{imgname.stem}___{image_set_id}___{time}.{ext}.jpg'

                    img_dst = Path(settings.MEDIA_ROOT).joinpath(fname)

                    write_file(img_dst, jpeg_img)

                finally:
                    output_io.close()




    # Synchronize database operations
    image_set = ImageSet.objects.get(id=image_set_id)
    image = Image(image_set=image_set, file_path=img_dst)
    image.save()


@staff_member_required
def image_upload(request, image_set_id):

    # Synchronous processing
    image_set = ImageSet.objects.get(id=image_set_id)
    form = ImageForm()
    if request.method == 'POST':
        form = ImageForm(request.POST, request.FILES)
        if form.is_valid():
            images = request.FILES.getlist('image')
            for img in images:
                # Synchronous processing
                process_image(img, image_set_id)
            return redirect('sortIT:choose_img_set')
    else:
        context = {
            'image_set': image_set,
            'form': form,
        }
        return TemplateResponse(request, 'sortIT/image_upload.html', context)


@staff_member_required
def download(request):

    if request.method == 'POST':
        user_id = request.POST['user']

        try:
            imageset_id = request.POST['imageset']
            imageset = ImageSet.objects.get(id=imageset_id)

        except MultiValueDictKeyError:
            users = User.objects.all()
            imagesets = ImageSet.objects.all()

            context = {
                'users': users,
                'imagesets': imagesets,
                'message': 'Please select an Image Set.',
            }
            return render(request, 'sortIT/download.html', context)

            
        delete = request.POST.get('delete', False)

        if request.POST.get('action') == 'download_images':
            user = User.objects.get(id=user_id)

            print(f"SELCTED IMAGESET: {imageset.name} ========================================")
            images = imageset.images.all()
            labels = imageset.label_set.all()

            labeled_images = images.filter(annotations__user=user)

            zip_name = f"{imageset.name}_{user.username}.zip"
            zip_path = Path(settings.MEDIA_ROOT).joinpath(zip_name)

            # generate ZIP
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                # For each label, get images linked to the label and add them to the corresponding folder in the ZIP file
                for label in labels:
                    # get images linked to the label
                    images_by_label = labeled_images.filter(annotations__label=label)

                    # Add images to the folder
                    for image in images_by_label:
                        image_filepath = Path(image.file_path)

                        ext = image_filepath.stem.split('.')[-1]
                        stem_image = image_filepath.stem.split('___')[0]
                        newname = f"{stem_image}.{ext}"

                        zip_file.write(image.file_path, Path(f'{imageset.name}_{user.username}').joinpath(label.name).joinpath(newname))

                        # If the checkbox is checked, delete the image from the database and server
                        if delete:
                            image.delete()

                            try:
                                os.remove(image_filepath)
                            except FileNotFoundError:
                                print(f'File Not found: {image_filepath}')
                                

            # Return the ZIP file as a response
            response = FileResponse(open(zip_path, 'rb'))
            response['Content-Type'] = 'application/zip'
            response['Content-Disposition'] = f'attachment; filename="{zip_name}"'

            os.remove(zip_path)

            return response

        elif request.POST.get('action') == 'download_csv':
            csv_generator = generate_csv_stream(separator=';', image_set=imageset)
            response = StreamingHttpResponse(csv_generator, content_type='text/csv')
            current_datetime = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            response['Content-Disposition'] = f'attachment; filename="image_set_{imageset}_{current_datetime}.csv"'
            return response

    else:
        users = User.objects.all()
        imagesets = ImageSet.objects.all()

        context = {
            'users': users,
            'imagesets': imagesets,
        }
        return render(request, 'sortIT/download.html', context)
