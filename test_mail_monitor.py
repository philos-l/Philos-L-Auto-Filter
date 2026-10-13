#!/usr/bin/env python3
"""
Test del Mail Keyword Monitor. Non servono credenziali: IMAP e Telegram
sono simulati.

Uso:
    python -m unittest -v
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import mail_monitor_multi as mm


def found(text, *keywords):
    return mm.matches(text, "", list(keywords))


class KeywordMatchTest(unittest.TestCase):

    def test_non_trova_dentro_una_parola(self):
        self.assertEqual(found("Phenomenological proposition", "logic", "position"), [])
        self.assertEqual(found("A position in logic", "logic", "position"),
                         ["logic", "position"])

    def test_trova_a_inizio_parola(self):
        self.assertEqual(found("Two PhD positions", "position"), ["position"])
        self.assertEqual(found("Kantian and logical themes", "kant", "logic"),
                         ["kant", "logic"])
        self.assertEqual(found("Two doctoral positions", "doctoral position"),
                         ["doctoral position"])

    def test_keyword_corta(self):
        self.assertEqual(found("The main claim", "AI"), [])
        self.assertEqual(found("Philosophy of AI.", "ai"), ["ai"])
        self.assertEqual(found("Aims and scope", "AI"), ["AI"])

    def test_maiuscole_e_punteggiatura(self):
        self.assertEqual(found("KANT's non-logical ethics", "kant", "logical"),
                         ["kant", "logical"])

    def test_frase_su_piu_spazi_o_righe(self):
        self.assertEqual(found("Call   for\nPapers", "call for papers"), ["call for papers"])

    def test_cerca_anche_nel_corpo(self):
        self.assertEqual(mm.matches("Subject", "about metaphysics", ["metaphysics"]),
                         ["metaphysics"])


class ExpressionTest(unittest.TestCase):

    REQUEST = ("(phd OR fellowship OR doctoral position) "
               "AND (metaphysics OR theoretical philosophy OR logic)")

    def test_and_di_or(self):
        self.assertEqual(found("PhD in theoretical philosophy", self.REQUEST),
                         ["phd", "theoretical philosophy"])
        self.assertEqual(found("PhD in ethics", self.REQUEST), [])
        self.assertEqual(found("Workshop on logic", self.REQUEST), [])

    def test_not(self):
        self.assertEqual(found("phd conference", "phd AND NOT conference"), [])
        self.assertEqual(found("phd school", "phd AND NOT conference"), ["phd"])

    def test_solo_not_mostra_l_espressione(self):
        self.assertEqual(found("anything", "NOT conference"), ["NOT conference"])

    def test_voci_in_or_senza_duplicati(self):
        self.assertEqual(found("phd in logic", "phd AND logic", "logic", "kant"),
                         ["phd", "logic"])

    def test_operatori_solo_in_maiuscolo(self):
        self.assertEqual(mm.parse_keyword("logic and language"), ("kw", "logic and language"))
        self.assertEqual(found("logic and language", "logic and language"),
                         ["logic and language"])

    def test_precedenza(self):
        self.assertEqual(
            mm.parse_keyword("a OR b AND NOT c"),
            ("or", [("kw", "a"), ("and", [("kw", "b"), ("not", ("kw", "c"))])]),
        )
        self.assertEqual(
            mm.parse_keyword("(a OR b) AND c"),
            ("and", [("or", [("kw", "a"), ("kw", "b")]), ("kw", "c")]),
        )

    def test_espressioni_malformate(self):
        for bad in ["", "(phd OR logic", "phd AND", "AND phd", "phd) OR x",
                    "()", "phd (logic)", "phd NOT x", "a OR OR b"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                mm.parse_keyword(bad)

    def test_check_keywords(self):
        self.assertEqual(mm.check_keywords({"keywords": ["phd", "(a OR b) AND c"]}), [])
        self.assertEqual(len(mm.check_keywords({"keywords": ["ok", 3, "(x"]})), 2)


class TextCleaningTest(unittest.TestCase):

    def test_normalize_subject(self):
        self.assertEqual(mm.normalize_subject("[PHILOS-L]  CFP: Kant "), "cfp: kant")

    def test_clean_body(self):
        body = ("CAUTION: This email originated outside. Be safe.\n"
                "Hello\n  world\n"
                'Philos-L "The Liverpool List" is run by ...')
        self.assertEqual(mm.clean_body(body), "Hello world")


def raw_mail(subject, body="", prefix="[PHILOS-L] "):
    return (f"Subject: {prefix}{subject}\r\nFrom: Someone <a@b.c>\r\n"
            f"Date: Mon, 1 Jan 2026 10:00:00 +0000\r\n\r\n{body}").encode()


class FakeIMAP:
    """Casella finta: `mails` è un dict UID -> mail grezza."""

    def __init__(self, mails):
        self.mails   = mails
        self.fetched = []

    def login(self, user, password):
        pass

    def select(self, label, readonly=False):
        return "OK", [b""]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b" ".join(str(u).encode() for u in sorted(self.mails))]
        uid = int(args[0])
        self.fetched.append(uid)
        return "OK", [(b"", self.mails[uid])]

    def logout(self):
        pass


class MainTest(unittest.TestCase):
    """Esegue main() su profili e stato temporanei, con IMAP e Telegram finti."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.profiles_dir = os.path.join(tmp.name, "profiles")
        self.state_dir    = os.path.join(tmp.name, "state")
        os.makedirs(self.profiles_dir)
        os.makedirs(self.state_dir)

        self.imap = FakeIMAP({
            1: raw_mail("PhD in logic"),
            2: raw_mail("Postdoc in ethics"),
            3: raw_mail("Workshop", body="A workshop on logic."),
        })
        self.send = mock.Mock()
        for patcher in (
            mock.patch.object(mm, "PROFILES_DIR", self.profiles_dir),
            mock.patch.object(mm, "STATE_DIR", self.state_dir),
            mock.patch.object(mm.imaplib, "IMAP4_SSL", lambda host: self.imap),
            mock.patch.object(mm, "fetch_archive_links", lambda: {}),
            mock.patch.object(mm, "send_telegram", self.send),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def add_profile(self, name, keywords, state=None):
        with open(os.path.join(self.profiles_dir, f"{name}.toml"), "w") as f:
            f.write(f"keywords = {json.dumps(keywords)}\ntelegram_chat_id = \"42\"\n")
        if state is not None:
            with open(os.path.join(self.state_dir, f"{name}.json"), "w") as f:
                json.dump(state, f)

    def state(self, name):
        path = os.path.join(self.state_dir, f"{name}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def run_main(self, *argv):
        """Ritorna il codice di uscita di main()."""
        out = io.StringIO()
        with mock.patch("sys.argv", ["mail_monitor_multi.py", *argv]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                mm.main()
            except SystemExit as e:
                return e.code
        return 0

    def sent_texts(self):
        return [call.args[2] for call in self.send.call_args_list]

    def test_notifica_solo_le_mail_nuove(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 1})
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.imap.fetched, [2, 3])
        self.assertEqual(len(self.sent_texts()), 1)
        self.assertIn("Workshop", self.sent_texts()[0])
        self.assertEqual(self.state("anna"), {"last_uid": 3})

    def test_legge_il_vecchio_formato_dello_stato(self):
        self.add_profile("anna", ["logic"], state={"seen_uids": ["2", "1"]})
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.imap.fetched, [3])
        self.assertEqual(self.state("anna"), {"last_uid": 3})

    def test_profilo_nuovo_riceve_solo_il_benvenuto(self):
        self.add_profile("nuovo", ["logic"])
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(self.imap.fetched, [])
        self.assertEqual(len(self.sent_texts()), 1)
        self.assertIn("Ciao", self.sent_texts()[0])
        self.assertEqual(self.state("nuovo"), {"last_uid": 3})

    def test_welcome_profilo_nuovo(self):
        self.add_profile("nuovo", ["logic", "(phd OR postdoc) AND kant"])
        self.assertEqual(self.run_main("--notify", "welcome", "--profile", "nuovo"), 0)
        self.assertEqual(self.imap.fetched, [])
        self.assertEqual(len(self.sent_texts()), 1)
        self.assertIn("(phd OR postdoc) AND kant", self.sent_texts()[0])
        self.assertEqual(self.state("nuovo"), {"last_uid": 3})

        # Il run giornaliero successivo non rimanda il benvenuto
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(self.sent_texts()), 1)

    def test_welcome_fallito_non_salva_lo_stato(self):
        self.add_profile("nuovo", ["logic"])
        self.send.side_effect = Exception("400 Bad Request: chat not found")
        self.assertEqual(self.run_main("--notify", "welcome", "--profile", "nuovo"), 1)
        self.assertIsNone(self.state("nuovo"))

    def test_welcome_profilo_esistente_non_tocca_lo_stato(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 1})
        self.assertEqual(self.run_main("--notify", "welcome", "--profile", "anna"), 0)
        self.assertEqual(len(self.sent_texts()), 1)
        self.assertEqual(self.state("anna"), {"last_uid": 1})

    def test_welcome_richiede_profile(self):
        self.add_profile("anna", ["logic"])
        self.assertEqual(self.run_main("--notify", "welcome"), 2)

    def test_avviso_modifica(self):
        self.add_profile("anna", ["logic", "kant"], state={"last_uid": 1})
        self.assertEqual(self.run_main("--notify", "modified", "--profile", "anna"), 0)
        self.assertIn("Parole chiave aggiornate", self.sent_texts()[0])
        self.assertIn("kant", self.sent_texts()[0])
        self.assertEqual(self.state("anna"), {"last_uid": 1})

    def test_avviso_reset_a_tutti_i_profili(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 0})
        self.add_profile("bruno", ["ethics"], state={"last_uid": 0})
        self.assertEqual(self.run_main("--notify", "reset"), 0)
        self.assertEqual(len(self.sent_texts()), 2)
        self.assertIn("Profilo resettato", self.sent_texts()[0])
        self.assertIn("ethics", self.sent_texts()[1])

    def test_avviso_rimozione_anche_con_keyword_non_valide(self):
        self.add_profile("anna", ["(logic OR"], state={"last_uid": 1})
        self.assertEqual(self.run_main("--notify", "removed", "--profile", "anna"), 0)
        self.assertIn("Profilo rimosso", self.sent_texts()[0])

    def test_avviso_fallito_non_blocca_l_operazione(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 1})
        self.send.side_effect = Exception("403 Forbidden: bot was blocked by the user")
        for kind in ("modified", "reset", "removed"):
            with self.subTest(kind=kind):
                self.assertEqual(self.run_main("--notify", kind, "--profile", "anna"), 0)
        self.assertEqual(self.state("anna"), {"last_uid": 1})

    def test_benvenuto_fallito_viene_ritentato(self):
        self.add_profile("nuovo", ["logic"])
        self.send.side_effect = Exception("403 Forbidden")
        self.assertEqual(self.run_main(), 1)
        self.assertIsNone(self.state("nuovo"))

    def test_reset_riscansiona_tutto(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 3})
        self.assertEqual(self.run_main("--reset", "--profile", "anna"), 0)
        self.assertEqual(self.state("anna"), {"last_uid": 0})
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(self.sent_texts()), 2)

    def test_invio_fallito_riprende_dalla_stessa_mail(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 0})
        self.send.side_effect = [None, Exception("429 Too Many Requests")]
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.state("anna"), {"last_uid": 2})

        self.send.reset_mock(side_effect=True)
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(len(self.sent_texts()), 1)
        self.assertIn("Workshop", self.sent_texts()[0])
        self.assertEqual(self.state("anna"), {"last_uid": 3})

    def test_un_invio_fallito_non_blocca_gli_altri_profili(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 0})
        self.add_profile("bruno", ["ethics"], state={"last_uid": 0})
        self.send.side_effect = [Exception("403 Forbidden"), None]
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.state("anna"), {"last_uid": 0})
        self.assertEqual(self.state("bruno"), {"last_uid": 3})

    def test_keyword_non_valide_saltano_solo_quel_profilo(self):
        self.add_profile("anna", ["(logic OR"], state={"last_uid": 0})
        self.add_profile("bruno", ["ethics"], state={"last_uid": 0})
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.state("anna"), {"last_uid": 0})
        self.assertEqual(self.state("bruno"), {"last_uid": 3})
        self.assertEqual(len(self.sent_texts()), 1)

    def test_check(self):
        self.add_profile("anna", ["(phd OR postdoc) AND logic"])
        self.assertEqual(self.run_main("--check"), 0)
        self.add_profile("bruno", ["phd AND"])
        self.assertEqual(self.run_main("--check"), 1)
        self.assertEqual(self.run_main("--check", "--profile", "anna"), 0)
        self.send.assert_not_called()

    def test_dry_run_non_invia_e_non_salva(self):
        self.add_profile("anna", ["logic"], state={"last_uid": 0})
        self.add_profile("nuovo", ["logic"])
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.send.assert_not_called()
        self.assertEqual(self.state("anna"), {"last_uid": 0})
        self.assertIsNone(self.state("nuovo"))

    def test_mail_non_della_lista_ignorate(self):
        self.imap.mails[4] = raw_mail("Spam about logic", prefix="")
        self.add_profile("anna", ["logic"], state={"last_uid": 3})
        self.assertEqual(self.run_main(), 0)
        self.send.assert_not_called()
        self.assertEqual(self.state("anna"), {"last_uid": 4})


if __name__ == "__main__":
    unittest.main()
