import unittest
from datetime import date, datetime
from studio.batch import plan, due, TZ
from studio.run import validate_job

class BatchChecks(unittest.TestCase):
    def test_twenty_pairings_cover_ten_days(self):
        pairs=[{'episode_id':f'CK{i+2:03}', 'batter':f'Batter {i}', 'bowler':'Bowler'} for i in range(20)]
        episodes=plan(pairs,date(2026,10,24))
        self.assertEqual(len({e['release_at'][:10] for e in episodes}),10)
        self.assertEqual(episodes[-1]['release_at'],'2026-11-02T22:00:00+05:30')
        self.assertEqual(len(due(episodes,datetime(2026,10,25,23,tzinfo=TZ))),2)
        self.assertEqual(due(episodes,datetime(2026,11,3,20,tzinfo=TZ)),[])

    def test_duplicate_and_flood_are_rejected(self):
        pairs=[{'episode_id':'CK002','batter':'Rohit Sharma','bowler':'Pat Cummins'}]*2
        with self.assertRaises(ValueError):plan(pairs,date(2026,10,24))
        episodes=[{'episode_id':f'CK{i+2:03}','release_at':'2026-10-24T12:00:00+05:30','privacy':'private'} for i in range(3)]
        with self.assertRaises(ValueError):due(episodes,datetime(2026,10,24,20,tzinfo=TZ))

    def test_private_only_and_wrong_legacy_identity(self):
        import json
        from pathlib import Path
        job=json.loads(Path('example-job.json').read_text())
        validate_job(job)
        job['privacy']='public'
        with self.assertRaises(ValueError):validate_job(job)
        job['privacy']='private';job['episode_id']='CK002'
        with self.assertRaises(ValueError):validate_job(job)

    def test_solo_attempt_stops_at_wicket_or_target(self):
        import json
        from pathlib import Path
        job=json.loads(Path('example-job.json').read_text())
        job.update(schema_version=2,episode_id='CK002',batter='Rohit Sharma',bowler='Pat Cummins',story_mode='empirical_what_if')
        for valid in ([0,'W'],[6,6],[0,1,0,1,0,1]):
            job['results']=valid;validate_job(job)
        for invalid in (['W',0],[6,6,0],[1,1]):
            job['results']=invalid
            with self.assertRaises(ValueError):validate_job(job)

class PublicationChecks(unittest.TestCase):
    def test_public_requires_explicit_opt_in(self):
        from unittest.mock import patch
        from studio.run import upload_metadata
        job={"title":"A what-if", "description":"AI illustrations"}
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(upload_metadata(job)["status"]["privacyStatus"], "private")
            with self.assertRaises(RuntimeError):upload_metadata(job,"public")
        with patch.dict("os.environ", {"CRICKET_PUBLIC_ENABLED":"true"}, clear=True):
            self.assertEqual(upload_metadata(job,"public")["status"]["privacyStatus"],"public")

    def test_public_schedule_matches_requested_slots(self):
        pairs=[{"episode_id":"CK003","batter":"Sachin","bowler":"Starc"},
               {"episode_id":"CK004","batter":"Warner","bowler":"Lee"}]
        episodes=plan(pairs,date(2026,10,24),privacy="public")
        self.assertEqual([e["release_at"][11:16] for e in episodes],["10:00","22:00"])
        self.assertEqual(len(due(episodes,datetime(2026,10,24,21,tzinfo=TZ))),1)
        self.assertEqual(len(due(episodes,datetime(2026,10,24,22,tzinfo=TZ))),2)

if __name__=='__main__': unittest.main()
