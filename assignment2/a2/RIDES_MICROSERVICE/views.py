from flask import Flask, request, Response, jsonify
from configure import db, areas, ip_port, users_hostname
import requests
from datetime import datetime

app = Flask(__name__)


@app.route('/api/v1/rides', methods=["POST"])
def create_ride():
    request_data = request.get_json(force=True)
    try:
        created_by = request_data['created_by']
        time_stamp = request_data['timestamp']
        source = int(request_data['source'])
        destination = int(request_data['destination'])
    except KeyError:
        # print("Inappropriate request received")
        return Response(status=400)

    try:
        req_date = convert_timestamp_to_datetime(time_stamp)
    except:
        # print("Invalid timestamp")
        return Response(status=400)

    if (source > len(areas) or destination > len(areas)) and (source < 1 or destination < 1):
        # print("Invalid source or destination")
        return Response(status=400)

    if not isUserPresent(created_by):
        print("User not present")
        return Response(status=400)

    try:
        f = open('seq.txt', 'r')
        ride_count = int(f.read())
        f.close()

        post_data = {
            "insert": [ride_count + 1, ride_count + 1, created_by, time_stamp, areas[source-1][1], areas[destination-1][1], []],
            "columns": ["_id", "rideId", "created_by", "timestamp", "source", "destination", "users"], "table": "rides"}
        response = requests.post('http://' + ip_port + '/api/v1/db/write', json=post_data)

        if response.status_code == 400:
            # print("Error while writing to database")
            return Response(status=400)
        else:
            f = open('seq.txt', 'w')
            f.write(str(ride_count + 1))
            f.close()
            return Response(status=201, response='{}', mimetype='application/json')
    except:
        # print("Error while writing to database")
        return Response(status=400)


@app.route('/api/v1/rides', methods=["GET"])
def list_rides_between_src_and_dst():
    source = request.args.get("source")
    destination = request.args.get("destination")

    if source is None or destination is None:
        # print("Inappropriate get parameters received")
        return Response(status=400)

    try:
        source = int(source)
        destination = int(destination)
    except:
        # print("Source and destination parameters must be integers")
        return Response(status=400)

    if (source > len(areas) or destination > len(areas)) and (source < 1 or destination < 1):
        # print("Areas not found")
        return Response(status=400)

    post_data = {"many": 1, "table": "rides", "columns": ["rideId", "created_by", "timestamp"],
                 "where": {"source": areas[source-1][1], "destination": areas[destination-1][1], "timestamp": {"$gt": convert_datetime_to_timestamp(datetime.now())}}}
    response = requests.post('http://' + ip_port + '/api/v1/db/read', json=post_data)

    if response.status_code == 400:
        return Response(status=400)

    result = response.json()
    for i in range(len(result)):
        if "_id" in result[i]:
            del result[i]["_id"]

    if not result:
        return Response(status=204)
    return jsonify(result)


@app.route('/api/v1/rides/<rideId>', methods=["GET", "POST", "DELETE"])
def get_details_of_ride_or_join_ride_or_delete_ride(rideId):
    try:
        a = int(rideId)
    except:
        return Response(status=400)

    if request.method == "GET":
        post_data = {"table": "rides",
                     "columns": ["rideId", "created_by", "users", "timestamp", "source", "destination"],
                     "where": {"rideId": int(rideId)}}
        response = requests.post('http://' + ip_port + '/api/v1/db/read', json=post_data)
        if response.text == "":
            return Response(status=204, response='{}', mimetype='application/json')
        res = response.json()
        del res["_id"]
        return jsonify(res)

    elif request.method == "POST":
        username = request.get_json(force=True)["username"]
        if not isUserPresent(username):
            # print("User not present")
            return Response(status=400)

        post_data = {"table": "rides", "where": {"rideId": int(rideId)}, "update": "users", "data": username,
                     "operation": "addToSet"}
        response = requests.post('http://' + ip_port + '/api/v1/db/write', json=post_data)
        if response.status_code == 400:
            return Response(status=400)
        return jsonify({})

    elif request.method == "DELETE":
        post_data = {'column': 'rideId', 'delete': int(rideId), 'table': 'rides'}
        response = requests.post('http://' + ip_port + '/api/v1/db/write', json=post_data)
        if response.status_code == 400:
            return Response(status=400)
        return jsonify({})


@app.route('/api/v1/list_rides/<username>', methods=["GET"])
def list_rides_created_or_joined_by_user(username):
    post_data = {"many": 1, "table": "rides", "columns": ['_id'], "where": {"$or": [{"users": username}, {"created_by": username}]}}
    response = requests.post('http://' + ip_port + '/api/v1/db/read', json=post_data)
    res = []
    print(response.json())
    for i in response.json():
        res.append(i['_id'])
    return jsonify(res)


@app.route('/api/v1/db/write', methods=["POST"])
def write_to_db():
    request_data = request.get_json(force=True)

    if 'delete' in request_data:
        try:
            delete = request_data['delete']
            column = request_data['column']
            collection = request_data['table']
        except KeyError:
            # print("Inappropriate request received")
            return Response(status=400)

        try:
            query = {column: delete}
            collection = db[collection]
            x = collection.delete_one(query)
            if x.raw_result['n'] == 1:
                return Response(status=200)
            return Response(status=400)
        except:
            # print("Mongo query failed")
            return Response(status=400)

    if 'update' in request_data:
        try:
            collection = request_data['table']
            where = request_data['where']
            array = request_data['update']
            data = request_data['data']
            operation = request_data['operation']
        except KeyError:
            # print("Inappropriate request received")
            return Response(status=400)

        try:
            collection = db[collection]
            x = collection.update_one(where, {"$" + operation: {array: data}})
            if x.raw_result['n'] == 1:
                return Response(status=200)
            return Response(status=400)
        except:
            return Response(status=400)

    try:
        insert = request_data['insert']
        columns = request_data['columns']
        collection = request_data['table']
    except KeyError:
        # print("Inappropriate request received")
        return Response(status=400)

    try:
        document = {}
        for i in range(len(columns)):
            if columns[i] == "timestamp":
                document[columns[i]] = convert_timestamp_to_datetime(insert[i])
            else:
                document[columns[i]] = insert[i]

        collection = db[collection]
        collection.insert_one(document)
        return Response(status=201)

    except:
        return Response(status=400)


@app.route('/api/v1/db/read', methods=["POST"])
def read_from_db():
    request_data = request.get_json(force=True)
    try:
        table = request_data['table']
        columns = request_data['columns']
        where = request_data['where']
    except KeyError:
        # print("Inappropriate request received")
        return Response(status=400)

    if "timestamp" in where:
        where["timestamp"]["$gt"] = convert_timestamp_to_datetime(where["timestamp"]["$gt"])

    filter = {}
    for i in columns:
        filter[i] = 1

    if 'many' in request_data:
        try:
            collection = db[table]
            res = []
            for i in collection.find(where, filter):
                if "timestamp" in i:
                    i["timestamp"] = convert_datetime_to_timestamp(i["timestamp"])
                res.append(i)

            return jsonify(res)
        except:
            return Response(status=400)

    try:
        collection = db[table]
        result = collection.find_one(where, filter)
        if "timestamp" in result:
            result["timestamp"] = convert_datetime_to_timestamp(result["timestamp"])
        return jsonify(result)
    except:
        return Response(status=400)


@app.route('/api/v1/db/clear', methods=["POST"])
def clear_db():
    collection1 = db["users"]
    collection2 = db["rides"]
    try:
        collection1.delete_many({})
        collection2.delete_many({})
        f = open("seq.txt", "w")
        f.write("0")
        f.close()
        return Response(status=200)
    except:
        return Response(status=400)


def isUserPresent(username):
    response = requests.get('http://' + users_hostname + '/api/v1/users')
    return response.status_code != 400 and username in response.json()


def convert_datetime_to_timestamp(k):
    day = str(k.day) if len(str(k.day)) == 2 else "0" + str(k.day)
    month = str(k.month) if len(str(k.month)) == 2 else "0" + str(k.month)
    year = str(k.year)
    second = str(k.second) if len(str(k.second)) == 2 else "0" + str(k.second)
    minute = str(k.minute) if len(str(k.minute)) == 2 else "0" + str(k.minute)
    hour = str(k.hour) if len(str(k.hour)) == 2 else "0" + str(k.hour)
    return day + "-" + month + "-" + year + ":" + second + "-" + minute + "-" + hour


def convert_timestamp_to_datetime(time_stamp):
    day = int(time_stamp[0:2])
    month = int(time_stamp[3:5])
    year = int(time_stamp[6:10])
    seconds = int(time_stamp[11:13])
    minutes = int(time_stamp[14:16])
    hours = int(time_stamp[17:19])
    return datetime(year, month, day, hours, minutes, seconds)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=80)
