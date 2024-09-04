import sys
import time
import queue
import threading
import subprocess
import customtkinter as ctk

from AudioRecorder import (DefaultMicRecorder, 
                           DefaultSpeakerRecorder)
from AudioTranscriber import AudioTranscriber
from GPTResponder import GPTResponder
import TranscriberModels


def write_in_textbox(textbox, text):
    textbox.delete("0.0", "end")
    textbox.insert("0.0", text)

def update_transcript_UI(transcriber, textbox):
    transcript_string = transcriber.get_transcript()
    write_in_textbox(textbox, transcript_string)
    textbox.after(300, update_transcript_UI, transcriber, textbox)

def update_response_UI(responder, textbox, update_interval_slider_label, update_interval_slider, freeze_state):
    if not freeze_state[0]:
        response = responder.response

        textbox.configure(state="normal")
        write_in_textbox(textbox, response)
        textbox.configure(state="disabled")

        update_interval = int(update_interval_slider.get())
        responder.update_response_interval(update_interval)
        update_interval_slider_label.configure(text=f"Update interval: {update_interval} seconds")

    textbox.after(300, update_response_UI, responder, textbox, update_interval_slider_label, update_interval_slider, freeze_state)

def clear_context(transcriber, audio_queue):
    transcriber.clear_transcript_data()
    with audio_queue.mutex:
        audio_queue.queue.clear()

def create_ui_components(root):
    # Set the appearance mode and color theme of the customtkinter application to dark mode with a dark-blue theme.
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    # Set the title of the main window and configure the background color and window size.
    root.title("Live Interview Assistant")
    root.configure(bg='#252422')
    root.geometry("1000x600")  # Set the window size to 1000x600 pixels.

    # Define a base font size to be used in the textboxes.
    font_size = 20

    # Create a textbox for displaying the transcript of the audio, with specified font, text color, and wrapping.
    transcript_textbox = ctk.CTkTextbox(root, width=300, font=("Arial", font_size), text_color='#FFFCF2', wrap="word")
    transcript_textbox.grid(row=0, column=0, padx=10, pady=20, sticky="nsew")  # Position the textbox in the grid.

    # Create a textbox for displaying the GPT model's responses, with specified font, text color, and wrapping.
    response_textbox = ctk.CTkTextbox(root, width=300, font=("Arial", font_size), text_color='#639cdc', wrap="word")
    response_textbox.grid(row=0, column=1, padx=10, pady=20, sticky="nsew")  # Position the textbox in the grid.

    # Create a button for freezing/unfreezing the transcript updates, positioned in the grid.
    freeze_button = ctk.CTkButton(root, text="Freeze", command=None)
    freeze_button.grid(row=1, column=1, padx=10, pady=3, sticky="nsew")

    # Create a label for displaying the update interval slider's value. Initially, the text is empty.
    update_interval_slider_label = ctk.CTkLabel(root, text=f"", font=("Arial", 12), text_color="#FFFCF2")
    update_interval_slider_label.grid(row=2, column=1, padx=10, pady=3, sticky="nsew")  # Position the label in the grid.

    # Create a slider to control the update interval for UI updates, with a range of 1 to 10 seconds.
    update_interval_slider = ctk.CTkSlider(root, from_=1, to=10, width=300, height=20, number_of_steps=9)
    update_interval_slider.set(2)  # Set the default value of the slider to 2 seconds.
    update_interval_slider.grid(row=3, column=1, padx=10, pady=10, sticky="nsew")  # Position the slider in the grid.

    # Return all created UI components as a tuple to be used in the main function.
    return (
        transcript_textbox, 
        response_textbox, 
        update_interval_slider, 
        update_interval_slider_label, 
        freeze_button
    )


def main():
    # Check if ffmpeg is installed, required for audio processing. If not, print an error and exit.
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("ERROR: The ffmpeg library is not installed. Please install ffmpeg and try again.")
        return


    # Initialize the main GUI window using customtkinter (CTk)
    root = ctk.CTk()
    # Create UI components (text boxes, sliders, buttons, etc.) and unpack them
    (transcript_textbox, 
     response_textbox, 
     update_interval_slider, 
     update_interval_slider_label, 
     freeze_button) = create_ui_components(root)


    # Create a queue to store audio data for processing
    audio_queue = queue.Queue()
    # Start recording from the user's microphone and push audio data to the queue
    user_audio_recorder = DefaultMicRecorder()
    user_audio_recorder.record_into_queue(audio_queue)
    # Sleep for 2 seconds to ensure the user audio recorder is initialized properly
    time.sleep(2)
    # Start recording from the system's speaker and push audio data to the queue
    speaker_audio_recorder = DefaultSpeakerRecorder()
    speaker_audio_recorder.record_into_queue(audio_queue)


    # Load the appropriate transcription model (potentially using an API)
    model = TranscriberModels.get_model('--api' in sys.argv)
    # Initialize the transcriber with both user and speaker audio sources and the chosen model
    transcriber = AudioTranscriber(user_audio_recorder.source, 
                                   speaker_audio_recorder.source, 
                                   model)
    # Start a background thread for transcribing the audio data from the queue
    transcribe = threading.Thread(target=transcriber.transcribe_audio_queue, 
                                  args=(audio_queue,))
    transcribe.daemon = True
    transcribe.start()


    # Initialize the GPT responder (likely a chat model) to generate responses based on the transcription
    responder = GPTResponder()
    # Start a background thread for responding to the transcriber outputs
    respond = threading.Thread(target=responder.respond_to_transcriber, 
                               args=(transcriber,))
    respond.daemon = True
    respond.start()


    # Print a message indicating the application is ready
    print("READY")
    # Configure the layout of the main window using a grid system
    root.grid_rowconfigure(0, weight=100)
    root.grid_rowconfigure(1, weight=1)
    root.grid_rowconfigure(2, weight=1)
    root.grid_rowconfigure(3, weight=1)
    root.grid_columnconfigure(0, weight=2)
    root.grid_columnconfigure(1, weight=1)
    # Add a "Clear Transcript" button to the UI and assign its command to clear the transcript and reset the queue
    clear_transcript_button = ctk.CTkButton(root, text="Clear Transcript", command=lambda: clear_context(transcriber, audio_queue))
    clear_transcript_button.grid(row=1, column=0, padx=10, pady=3, sticky="nsew")

    # Initialize a state for freezing/unfreezing the response updates (using a list to allow mutable state change)
    freeze_state = [False]  # Using list to be able to change its content inside inner functions
    # Define a function to toggle the freeze state and update the button text accordingly
    def freeze_unfreeze():
        freeze_state[0] = not freeze_state[0]  # Invert the freeze state
        freeze_button.configure(text="Unfreeze" if freeze_state[0] else "Freeze")
    # Assign the freeze/unfreeze function to the freeze button's command
    freeze_button.configure(command=freeze_unfreeze)

    # Update the label showing the current value of the update interval slider
    update_interval_slider_label.configure(text=f"Update interval: {update_interval_slider.get()} seconds")


    # Start updating the transcript and response text boxes in the UI
    update_transcript_UI(transcriber, transcript_textbox)
    update_response_UI(responder, response_textbox, update_interval_slider_label, update_interval_slider, freeze_state)
 
    # Start the Tkinter main loop to keep the GUI running
    root.mainloop()


if __name__ == "__main__":
    main()