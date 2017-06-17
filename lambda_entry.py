from __future__ import print_function

import boto3
import json
import praw
import os

import roll_one

def respond(err, res=None):
    return {
        'statusCode': '400' if err else '200',
        'body': err.message if err else json.dumps(res),
        'headers': {
            'Content-Type': 'application/json',
        },
    }


def lambda_handler(event, context):
    params = event['params']
    kwargs = dict(
        search_term=params['search_term'],
        sub_id=params.get('sub_id', None),
    )
    table = roll_one.find_table(roll_one.sign_in(), **kwargs)
    payload = table.for_json() if table else {}
    return respond(None, payload)
