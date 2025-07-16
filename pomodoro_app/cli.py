import os
import json
import base64
import click
from flask.cli import with_appcontext
from .agent_config import load_personas, save_personas


@click.group()
def personas():
    """Manage agent personas."""
    pass


@personas.command('list')
@with_appcontext
def list_personas():
    """List configured agent personas."""
    data = load_personas()
    click.echo(json.dumps(data, indent=2))


@personas.command('set')
@click.argument('name')
@click.option('--prompt', required=True, help='Prompt for the persona')
@click.option('--voice', required=True, help='TTS voice name')
@with_appcontext
def set_persona(name, prompt, voice):
    """Add or update an agent persona."""
    data = load_personas()
    data[name] = {'prompt': prompt, 'voice': voice}
    save_personas(data)
    click.echo(f"Persona '{name}' saved.")


@click.group()
def secrets():
    """Secret key utilities."""
    pass


@secrets.command('generate-key')
@click.option('--bytes', 'num_bytes', default=32, show_default=True,
              help='Number of random bytes to use')
def generate_key(num_bytes):
    """Generate a base64-encoded SECRET_KEY."""
    key = base64.b64encode(os.urandom(num_bytes)).decode()
    click.echo(key)
