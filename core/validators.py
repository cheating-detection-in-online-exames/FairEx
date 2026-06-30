import os 

# ---------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_AUDIO_EXTENSIONS = {'webm', 'mp3', 'wav', 'ogg'}

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB general limit

# Audio Limit: 150KB is approx 8-10 seconds of voice audio
# This is a safe buffer for a "5 second" recording
MAX_AUDIO_SIZE = 50 * 1024 


# ---------------------------------------------------
# FUNCTIONS
# ---------------------------------------------------

def allowed_file(filename):

    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def allowed_file(filename, file_type='image'):
    print ("hiiiiiiiiiiii----------------------------------->")
    if '.' not in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()

    if file_type == 'image':
        print ("hiiiiiiiiiiii----------------------------------in tothtrlk.kfjvbwrfkuv->")
        return ext in ALLOWED_IMAGE_EXTENSIONS
    elif file_type == 'audio':
        return ext in ALLOWED_AUDIO_EXTENSIONS
    
    return False


def allowed_file_size(file):
    """Checks the general 5MB limit for any file"""
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0, os.SEEK_SET) # Reset cursor
    return file_size <= MAX_FILE_SIZE_BYTES


def validate_audio_recording(file):
    """
    Specifically checks if the audio recording is short enough.
    We use size because browser-recorded WebM files often 
    don't have duration headers, making libraries like mutagen fail.
    """
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0, os.SEEK_SET) # Reset cursor (CRITICAL)
    
    if size > MAX_AUDIO_SIZE:
        return False, "Audio is too long (keep it under 5-10 seconds)"
    
    return True, "Audio OK"

