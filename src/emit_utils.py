from flask_socketio import SocketIO

# Global SocketIO instance
socketio = None

def set_socketio_instance(instance):
    """Set the global SocketIO instance"""
    global socketio
    socketio = instance

def emit_message(message, message_type="info"):
    """Emit a message through SocketIO if available"""
    if socketio:
        try:
            socketio.emit('status_message', {
                'message': message,
                'type': message_type
            })
        except Exception as e:
            print(f"Error emitting message: {str(e)}")
    else:
        print(f"SocketIO not initialized. Message: {message} ({message_type})")

def emit_progress(progress):
    """Emit progress through SocketIO if available"""
    if socketio:
        try:
            socketio.emit('progress', {
                'progress': progress
            })
        except Exception as e:
            print(f"Error emitting progress: {str(e)}")
    else:
        print(f"SocketIO not initialized. Progress: {progress}")

def emit_download_complete(data):
    """Emit download complete through SocketIO if available"""
    if socketio:
        try:
            socketio.emit('download_complete', data)
        except Exception as e:
            print(f"Error emitting download complete: {str(e)}")
    else:
        print(f"SocketIO not initialized. Download complete data: {data}")
